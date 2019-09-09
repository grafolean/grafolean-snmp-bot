import sys
import requests
import logging
import time
import math
from datetime import datetime, timedelta
from pytz import utc
from abc import abstractmethod

import concurrent.futures
import traceback

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.executors.base import BaseExecutor
from apscheduler.events import (
    JobExecutionEvent, EVENT_JOB_MISSED, EVENT_JOB_ERROR, EVENT_JOB_EXECUTED)


class MultipleIntervalsTrigger(BaseTrigger):
    """
        This is a class extends APScheduler's BaseTrigger:
        - triggers at multiple intervals
        - aligns every invocation to a second (to make calculation of intervals easier)
        - multiple intervals, when aligned, cause only a single job invocation
        - remembers which intervals have caused the invocation; the list is cleared after
          `forget_affecting_after` seconds
    """
    __slots__ = 'intervals', 'start_ts', 'affecting_intervals', 'forget_affecting_after'

    def __init__(self, intervals, forget_affecting_after=300):
        if not intervals:
            raise Exception("At least one interval must be specified")
        # we only operate in whole seconds, and only care about unique values:
        self.intervals = list(set([int(i) for i in intervals]))
        self.forget_affecting_after = forget_affecting_after
        self.start_ts = int(time.time())
        self.affecting_intervals = {}

    def get_next_fire_time(self, previous_fire_time, now):
        # We keep things simple by only dealing with UTC, and only with seconds, so
        # when travelling at low speeds we can use UNIX timestamps pretty safely.
        elapsed_time = now.timestamp() - self.start_ts
        # find the first time one of the intervals should fire:
        next_fires_for_intervals = [int(math.ceil(elapsed_time / interval) * interval) for interval in self.intervals]
        min_next_fire = min(next_fires_for_intervals)

        # This is a hack. APScheduler doesn't allow us to pass information about the intervals triggered to the job being executed,
        # so we remember this information in the trigger object itself, which we then pass as a parameter to the executed job. Not
        # ideal, but it allows us to pass this information.
        # Determine which intervals will cause the next fire:
        next_fire_ts = self.start_ts + min_next_fire
        self.affecting_intervals[next_fire_ts] = []
        for i, next_fire_for_interval in enumerate(next_fires_for_intervals):
            if next_fire_for_interval == min_next_fire:
                self.affecting_intervals[next_fire_ts].append(self.intervals[i])

        self._cleanup(now.timestamp() - self.forget_affecting_after)
        return datetime.fromtimestamp(next_fire_ts, tz=utc)

    def _cleanup(self, limit_ts):
        for ts in list(self.affecting_intervals.keys()):
            if ts < limit_ts:
                del self.affecting_intervals[ts]


class IntervalsAwareProcessPoolExecutor(BaseExecutor):
    """
        This class merges APScheduler's BasePoolExecutor and ProcessPoolExecutor,
        because we need to use our own version of `run_job` (with a small detail
        changed - additional parameter passed). Unfortunately there is probably no
        cleaner way to do this at the moment.
    """
    def __init__(self, max_workers=10):
        super().__init__()
        self._pool = concurrent.futures.ProcessPoolExecutor(int(max_workers))

    def _do_submit_job(self, job, run_times):
        """
        This function is copy-pasted from apscheduler/executors/pool.py
        (`BasePoolExecutor._do_submit_job()`). The difference is that it calls our own
        version of `run_job`.
        """
        def callback(f):
            exc, tb = (f.exception_info() if hasattr(f, 'exception_info') else
                       (f.exception(), getattr(f.exception(), '__traceback__', None)))
            if exc:
                self._run_job_error(job.id, exc, tb)
            else:
                self._run_job_success(job.id, f.result())

        f = self._pool.submit(IntervalsAwareProcessPoolExecutor.run_job, job, job._jobstore_alias, run_times, self._logger.name)
        f.add_done_callback(callback)

    def shutdown(self, wait=True):
        self._pool.shutdown(wait)

    @staticmethod
    def run_job(job, jobstore_alias, run_times, logger_name):
        """
        This function is copy-pasted from apscheduler/executors/base.py (`run_job()`). It is defined
        as static method here, and only the invocation of the job (`job.func()` call) was changed.

        The reason for this is that we need to pass `affecting_intervals` from the trigger to the job
        function, so it can decide which parts of the job need to be run. SNMPCollector needs this
        so it can fetch data either separately, or for all of the task at the same time, when their
        intervals align.

        The changes are in a single block and are marked with a comment.

        ---
        Called by executors to run the job. Returns a list of scheduler events to be dispatched by the
        scheduler.
        """
        events = []
        logger = logging.getLogger(logger_name)
        for run_time in run_times:
            # See if the job missed its run time window, and handle
            # possible misfires accordingly
            if job.misfire_grace_time is not None:
                difference = datetime.now(utc) - run_time
                grace_time = timedelta(seconds=job.misfire_grace_time)
                if difference > grace_time:
                    events.append(JobExecutionEvent(EVENT_JOB_MISSED, job.id, jobstore_alias,
                                                    run_time))
                    logger.warning('Run time of job "%s" was missed by %s', job, difference)
                    continue

            logger.info('Running job "%s" (scheduled at %s)', job, run_time)
            try:
                ##########################
                ### changes
                ##########################
                # retval = job.func(*job.args, **job.kwargs)
                affecting_intervals = job.trigger.affecting_intervals[run_time.timestamp()]
                retval = job.func(affecting_intervals, **job.kwargs)
                ##########################
                ### /changes
                ##########################
            except BaseException:
                exc, tb = sys.exc_info()[1:]
                formatted_tb = ''.join(traceback.format_tb(tb))
                events.append(JobExecutionEvent(EVENT_JOB_ERROR, job.id, jobstore_alias, run_time,
                                                exception=exc, traceback=formatted_tb))
                logger.exception('Job "%s" raised an exception', job)

                # This is to prevent cyclic references that would lead to memory leaks
                traceback.clear_frames(tb)
                del tb
            else:
                events.append(JobExecutionEvent(EVENT_JOB_EXECUTED, job.id, jobstore_alias, run_time,
                                                retval=retval))
                logger.info('Job "%s" executed successfully', job)

        return events


class Collector(object):
    __slots__ = 'backend_url', 'bot_token'

    def __init__(self, backend_url, bot_token):
        self.backend_url = backend_url
        self.bot_token = bot_token

    @abstractmethod
    def jobs(self):
        """
            Returns a list of (intervals, job_func, job_data) tuples. Usually calls
            `fetch_job_configs` to get input data.
        """

    def fetch_job_configs(self, protocol):
        """
            Returns pairs (account_id, entity_info), where entity_info is everything needed for collecting data
            from the entity - credentials and list of sensors (with intervals) for selected protocol.
            The data is cleaned up as much as possible, so that it only contains the things necessary for collectors
            to do their job.
        """
        # find all the accounts we have access to:
        r = requests.get('{}/accounts/?b={}'.format(self.backend_url, self.bot_token))
        if r.status_code != 200:
            raise Exception("Invalid bot token or network error, got status {} while retrieving {}/accounts".format(r.status_code, self.backend_url))
        j = r.json()
        accounts_ids = [a["id"] for a in j["list"]]

        # find all entities for each of the accounts:
        for account_id in accounts_ids:
            r = requests.get('{}/accounts/{}/entities/?b={}'.format(self.backend_url, account_id, self.bot_token))
            if r.status_code != 200:
                raise Exception("Network error, got status {} while retrieving {}/accounts/{}/entities".format(r.status_code, self.backend_url, account_id))
            j = r.json()
            entities_ids = [e["id"] for e in j["list"]]

            for entity_id in entities_ids:
                r = requests.get('{}/accounts/{}/entities/{}?b={}'.format(self.backend_url, account_id, entity_id, self.bot_token))
                if r.status_code != 200:
                    raise Exception("Network error, got status {} while retrieving {}/accounts/{}/entities/{}".format(r.status_code, self.backend_url, account_id, entity_id))
                entity_info = r.json()

                # make sure that the protocol is enabled on the entity:
                if protocol not in entity_info["protocols"]:
                    continue
                # and that credential is set:
                if not entity_info["protocols"][protocol]["credential"]:
                    continue
                credential_id = entity_info["protocols"][protocol]["credential"]
                # and that there is at least one sensor enabled for this protocol:
                if not entity_info["protocols"][protocol]["sensors"]:
                    continue

                r = requests.get('{}/accounts/{}/credentials/{}?b={}'.format(self.backend_url, account_id, credential_id, self.bot_token))
                if r.status_code != 200:
                    raise Exception("Network error, got status {} while retrieving {}/accounts/{}/credentials/{}".format(r.status_code, self.backend_url, account_id, credential_id))
                credential = r.json()
                entity_info["credential_details"] = credential["details"]

                sensors = []
                for sensor_info in entity_info["protocols"][protocol]["sensors"]:
                    sensor_id = sensor_info["sensor"]
                    r = requests.get('{}/accounts/{}/sensors/{}?b={}'.format(self.backend_url, account_id, sensor_id, self.bot_token))
                    if r.status_code != 200:
                        raise Exception("Network error, got status {} while retrieving {}/accounts/{}/sensors/{}".format(r.status_code, self.backend_url, account_id, sensor["sensor"]))
                    sensor = r.json()

                    # determine interval, since this part is generic:
                    if sensor_info["interval"] is not None:
                        interval = sensor_info["interval"]
                    elif sensor["default_interval"] is not None:
                        interval = sensor["default_interval"]
                    else:
                        logging.warn("Interval not set, ignoring sensor {} on entity {}!".format(sensor_id, entity_id))
                        continue
                    del sensor["default_interval"]  # cleanup - nobody should need this anymore

                    sensors.append({
                        "sensor_details": sensor["details"],
                        "interval": interval,
                    })
                # and hide all other protocols, saving just sensors for selected one: (not strictly necessary, just cleaner)
                entity_info["sensors"] = sensors
                del entity_info["protocols"]

                entity_info["account_id"] = account_id

                yield entity_info

    def execute(self):
        """
            Calls self.jobs() to get the list of the jobs, and executes them by using
            `MultipleIntervalsTrigger`. Blocking.
        """
        # initialize APScheduler:
        job_defaults = {
            'coalesce': True,  # if multiple jobs "misfire", re-run only one instance of a missed job
            'max_instances': 1,
        }
        scheduler = BlockingScheduler(job_defaults=job_defaults, timezone=utc)
        executor = IntervalsAwareProcessPoolExecutor(10)
        scheduler.add_executor(executor, 'iaexecutor')

        for intervals, job_func, job_data in self.jobs():
            trigger = MultipleIntervalsTrigger(intervals)
            scheduler.add_job(job_func, trigger=trigger, executor='iaexecutor', kwargs=job_data)

        try:
            scheduler.start()
        except KeyboardInterrupt:
            logging.info("Got exit signal, exiting.")
