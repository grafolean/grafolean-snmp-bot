import os
import dotenv
import logging
import json
import time
from pytz import utc
from colors import color
import requests
import redis

from easysnmp import Session, SNMPVariable
from mathjspy import MathJS

from collector import Collector


logging.basicConfig(format='%(asctime)s | %(levelname)s | %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S', level=logging.DEBUG)
logging.addLevelName(logging.DEBUG, color("DBG", 7))
logging.addLevelName(logging.INFO, "INF")
logging.addLevelName(logging.WARNING, color('WRN', fg='red'))
logging.addLevelName(logging.ERROR, color('ERR', bg='red'))
log = logging.getLogger("{}.{}".format(__name__, "base"))


class NoValueForOid(Exception):
    pass


REDIS_HOST = os.environ.get('REDIS_HOST', '127.0.0.1')
r = redis.Redis(host=REDIS_HOST)


def _get_previous_counter_value(counter_ident):
    prev_value = r.hgetall(counter_ident)
    if not prev_value:  # empty dict
        return None, None
    return int(float(prev_value[b'v'])), float(prev_value[b't'])


def _save_current_counter_value(new_value, now, counter_ident):
    r.hmset(counter_ident, {b'v': new_value, b't': now})


def _convert_counters_to_values(results, now, counter_ident_prefix):
    new_results = []
    for i, v in enumerate(results):
        if isinstance(v, list):
            new_results.append(_convert_counters_to_values(v, now, counter_ident_prefix + f'/{i}'))
            continue
        if v.snmp_type not in ['COUNTER', 'COUNTER64']:
            new_results.append(v)
            continue
        # counter - deal with it:
        counter_ident = counter_ident_prefix + f'/{i}/{v.oid}/{v.oid_index}'
        old_value, t = _get_previous_counter_value(counter_ident)
        new_value = float(v.value)
        _save_current_counter_value(new_value, now, counter_ident)
        if old_value is None:
            new_results.append(SNMPVariable(oid=v.oid, oid_index=v.oid_index, value=None, snmp_type='COUNTER_PER_S'))
            continue

        # it seems like the counter overflow happened, discard result:
        if new_value < old_value:
            new_results.append(SNMPVariable(oid=v.oid, oid_index=v.oid_index, value=None, snmp_type='COUNTER_PER_S'))
            log.warning(f"Counter overflow detected for oid {v.oid}, oid index {v.oid_index}, discarding value - if this happens often, consider using OIDS with 64bit counters (if available) or decreasing polling interval.")
            continue

        dt = now - t
        dv = (new_value - old_value) / dt
        new_results.append(SNMPVariable(oid=v.oid, oid_index=v.oid_index, value=dv, snmp_type='COUNTER_PER_S'))
    return new_results


def _apply_expression_to_results(snmp_results, methods, expression, output_path):
    if 'walk' in methods:
        """
            - determine which oid indexes are used
            - rearrange SNMP results so that they are in dicts, addressable by oid_indexes
            - for each oid_index, calculate expression value
        """
        walk_indexes = [v.oid_index for v in snmp_results[methods.index('walk')]]

        addressable_results = []
        for i, snmp_result in enumerate(snmp_results):
            if methods[i] == 'get':
                # GET value is used n-times, to simulate walk
                addressable_results.append({oid_index: snmp_result for oid_index in walk_indexes})
            elif methods[i] == 'walk':
                addressable_results.append({o.oid_index: o for o in snmp_result})

        result = []
        for oid_index in walk_indexes:
            try:
                mjs = MathJS()
                for i, r in enumerate(addressable_results):
                    v = r.get(oid_index)
                    if v is None:  # oid index wasn't present
                        raise NoValueForOid()
                    if v.value is None:  # no value (probably the first time we're asking for a counter)
                        raise NoValueForOid()
                    mjs.set('${}'.format(i + 1), float(v.value))
                value = mjs.eval(expression)
                result.append({
                    'p': f'{output_path}.{oid_index}',
                    'v': value,
                })
            except NoValueForOid:
                log.warning(f'Missing value for oid index: {oid_index}')
        return result

    else:
        try:
            mjs = MathJS()
            for i, v in enumerate(snmp_results):
                if v.value is None:  # no value (probably the first time we're asking for a counter)
                    raise NoValueForOid()
                mjs.set('${}'.format(i + 1), float(v.value))
            value = mjs.eval(expression)
            return [
                {'p': output_path, 'v': value},
            ]
        except NoValueForOid:
            log.warning(f'Missing OID value (counter?)')
            return []


def send_results_to_grafolean(backend_url, bot_token, account_id, values):
    url = '{}/accounts/{}/values/?b={}'.format(backend_url, account_id, bot_token)

    log.info("Sending results to Grafolean")
    try:
        r = requests.post(url, json=values)
        r.raise_for_status()
        log.info("Results sent: {}".format(values))
    except:
        log.exception("Error sending data to Grafolean")


class SNMPCollector(Collector):

    @staticmethod
    def do_snmp(*args, **job_info):
        """
            {
                "entity_id": 1348300224,
                "name": "localhost",
                "entity_type": "device",
                "details": {
                    "ipv4": "127.0.0.1"
                },
                "credential_details": {
                    "version": "snmpv1",
                    "snmpv12_community": "public"
                },
                "sensors": [
                    {
                        "sensor_details": {
                            "oids": [
                                {
                                    "oid": "1.3.6.1.4.1.2021.13.16.2.1.3",
                                    "fetch_method": "walk"
                                }
                            ],
                            "expression": "$1",
                            "output_path": "lm-sensors"
                        },
                        "interval": 30
                    },
                    {
                        "sensor_details": {
                            "oids": [
                                {
                                    "oid": "1.3.6.1.4.1.2021.13.16.2.1.3.5",
                                    "fetch_method": "get"
                                }
                            ],
                            "expression": "$1",
                            "output_path": "lmsensorscore3"
                        },
                        "interval": 20
                    }
                ],
                "account_id": 1
            }
        """
        log.info("Running job for account [{account_id}], IP [{ipv4}]".format(
            account_id=job_info["account_id"],
            ipv4=job_info["details"]["ipv4"],
        ))

        # filter out only those sensors that are supposed to run at this interval:
        affecting_intervals, = args

        # initialize session:
        session_kwargs = {
            "hostname": job_info["details"]["ipv4"],
            "use_numeric": True,
        }
        cred = job_info["credential_details"]
        snmp_version = int(cred["version"][5:6])
        session_kwargs["version"] = snmp_version
        if snmp_version in [1, 2]:
            session_kwargs["community"] = cred["snmpv12_community"]
        elif snmp_version == 3:
            session_kwargs = {
                **session_kwargs,
                "security_username": cred["snmpv3_securityName"],
                "security_level": cred["snmpv3_securityLevel"],  # easysnmp supports camelCase level names too
                "privacy_protocol": cred.get("snmpv3_privProtocol", 'DEFAULT'),
                "privacy_password": cred.get("snmpv3_privKey", ''),
                "auth_protocol": cred.get("snmpv3_authProtocol", 'DEFAULT'),
                "auth_password": cred.get("snmpv3_authKey", ''),
            }
        else:
            raise Exception("Invalid SNMP version")

        session = Session(**session_kwargs)

        activated_sensors = [s for s in job_info["sensors"] if s["interval"] in affecting_intervals]
        for sensor in activated_sensors:
            results = []
            oids = [o["oid"] for o in sensor["sensor_details"]["oids"]]
            methods = [o["fetch_method"] for o in sensor["sensor_details"]["oids"]]
            walk_indexes = None
            for oid, fetch_method in zip(oids, methods):
                if fetch_method == 'get':
                    result = session.get(oid)
                    results.append(result)
                else:
                    result = session.walk(oid)
                    results.append(result)
                    # while we are at it, save the indexes of the results:
                    if not walk_indexes:
                        walk_indexes = [r.oid_index for r in result]
            log.info("Results: {}".format(list(zip(oids, methods, results))))

            counter_ident_prefix = f'{job_info["entity_id"]}/{sensor["sensor_id"]}'
            results_no_counters = _convert_counters_to_values(results, time.time(), counter_ident_prefix)

            # We have SNMP results and expression - let's calculate value(s). The trick here is that
            # if some of the data is fetched via SNMP WALK, we will have many results; if only SNMP
            # GET was used, we get one.
            expression = sensor["sensor_details"]["expression"]
            output_path = f'entity.{job_info["entity_id"]}.snmp.{sensor["sensor_details"]["output_path"]}'
            values = _apply_expression_to_results(results_no_counters, methods, expression, output_path)
            send_results_to_grafolean(job_info['backend_url'], job_info['bot_token'], job_info['account_id'], values)


    def jobs(self):
        """
            Each entity (device) is a single job, no matter how many sensors it has. The reason is
            that when the intervals align, we can then issue a single SNMP Bulk GET/WALK.
        """
        for entity_info in self.fetch_job_configs('snmp'):
            intervals = list(set([sensor_info["interval"] for sensor_info in entity_info["sensors"]]))
            job_info = { **entity_info, "backend_url": self.backend_url, "bot_token": self.bot_token }
            job_id = str(entity_info["entity_id"])
            yield job_id, intervals, SNMPCollector.do_snmp, job_info


if __name__ == "__main__":
    dotenv.load_dotenv()

    backend_url = os.environ.get('BACKEND_URL')
    bot_token = os.environ.get('BOT_TOKEN')
    if not backend_url or not bot_token:
        raise Exception("Please specify BACKEND_URL and BOT_TOKEN env vars.")
    jobs_refresh_interval = int(os.environ.get('JOBS_REFRESH_INTERVAL', 120))

    c = SNMPCollector(backend_url, bot_token, jobs_refresh_interval)
    c.execute()
