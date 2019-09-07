from apscheduler.schedulers.blocking import BlockingScheduler
import os
import dotenv
import logging
from pytz import utc
from colors import color


from collector import Collector


logging.basicConfig(format='%(asctime)s | %(levelname)s | %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S', level=logging.DEBUG)
logging.addLevelName(logging.DEBUG, color("DBG", 7))
logging.addLevelName(logging.INFO, "INF")
logging.addLevelName(logging.WARNING, color('WRN', fg='red'))
logging.addLevelName(logging.ERROR, color('ERR', bg='red'))
log = logging.getLogger("{}.{}".format(__name__, "base"))


class SNMPCollector(Collector):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.jobs_configs = []
        for account_id, entity_info in self.fetch_job_configs('snmp'):
            # convert entity_info into easy-to-use task definitions:
            for sensor_info in entity_info["sensors"]:
                self.jobs_configs.append({
                    "account_id": account_id,
                    "entity": entity_info["details"],
                    "sensor": sensor_info["sensor_details"],
                    "interval": sensor_info["interval"],
                    "credential": entity_info["credential_details"],
                })

            # >>> import json
            # >>> print(json.dumps(self.jobs_configs))
            # [
            #     {
            #         "account_id": 1,
            #         "entity": {
            #             "ipv4": "127.0.0.1"
            #         },
            #         "sensor": {
            #             "oids": [
            #                 {
            #                     "oid": "1.3.6.1.4.1.2021.13.16.2.1.3",
            #                     "fetch_method": "get"
            #                 }
            #             ],
            #             "expression": "$1",
            #             "output_path": "lm-sensors"
            #         },
            #         "interval": 30,
            #         "credential": {
            #             "version": "snmpv1",
            #             "snmpv12_community": "public"
            #         }
            #     }
            # ]

    @staticmethod
    def do_snmp(account_id, entity, sensor, interval, credential):
        log.info("Running job for account [{account_id}], IP [{ipv4}], OIDS: {oids}".format(
            account_id=account_id,
            ipv4=entity["ipv4"],
            oids=["SNMP{} {}".format(o["fetch_method"].upper(), o["oid"]) for o in sensor["oids"]],
        ))

    def execute(self):
        # initialize a scheduler:
        job_defaults = {
            'coalesce': True,  # if multiple jobs "misfire", re-run only one instance of a missed job
            'max_instances': 1,
        }
        self.scheduler = BlockingScheduler(job_defaults=job_defaults, timezone=utc)

        # apply config to scheduler:
        for job_config in self.jobs_configs:
            self.scheduler.add_job(SNMPCollector.do_snmp, 'interval', seconds=job_config["interval"], kwargs=job_config)

        try:
            self.scheduler.start()
        except KeyboardInterrupt:
            log.info("Got exit signal, exiting.")

if __name__ == "__main__":
    dotenv.load_dotenv()

    backend_url = os.environ.get('BACKEND_URL')
    bot_token = os.environ.get('BOT_TOKEN')
    if not backend_url or not bot_token:
        raise Exception("Please specify BACKEND_URL and BOT_TOKEN env vars.")

    c = SNMPCollector(backend_url, bot_token)
    c.execute()
