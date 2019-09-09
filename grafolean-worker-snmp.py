import os
import dotenv
import logging
import json
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

    @staticmethod
    def do_snmp(*args, **entity_info):
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
        # filter out only those sensors that are supposed to run at this interval:
        affecting_intervals, = args
        sensors = [s for s in entity_info["sensors"] if s["interval"] in affecting_intervals]
        oids = []
        for sensor in sensors:
            oids.extend(sensor["sensor_details"]["oids"])
        log.info("Running job for account [{account_id}], IP [{ipv4}], nsensors: {n_sensors}, oids: {oids}".format(
            account_id=entity_info["account_id"],
            ipv4=entity_info["details"]["ipv4"],
            n_sensors=len(sensors),
            oids=["SNMP{} {}".format(o["fetch_method"].upper(), o["oid"]) for o in oids],
        ))



    def jobs(self):
        """
            Each entity (device) is a single job, no matter how many sensors it has. The reason is
            that when the intervals align, we can then issue a single SNMP Bulk GET/WALK.
        """
        for entity_info in self.fetch_job_configs('snmp'):
            intervals = list(set([sensor_info["interval"] for sensor_info in entity_info["sensors"]]))
            yield intervals, SNMPCollector.do_snmp, entity_info


if __name__ == "__main__":
    dotenv.load_dotenv()

    backend_url = os.environ.get('BACKEND_URL')
    bot_token = os.environ.get('BOT_TOKEN')
    if not backend_url or not bot_token:
        raise Exception("Please specify BACKEND_URL and BOT_TOKEN env vars.")

    c = SNMPCollector(backend_url, bot_token)
    c.execute()
