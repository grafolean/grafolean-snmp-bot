import os
import dotenv
import logging
import json
from pytz import utc
from colors import color

from easysnmp import Session

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
            for oid, fetch_method in zip(oids, methods):
                if fetch_method == 'get':
                    result = session.get(oid)
                    results.append(result)
                else:
                    result = session.walk(oid)
                    results.append(result)
            oids_results = list(zip(oids, methods, results))
            log.info("Results: {}".format(oids_results))




            # SNMPCollector.send_results_to_grafolean(
            #     job_info["base_url"],
            #     job_info["bot_token"],
            #     job_info["account_id"],
            #     job_info["entity_id"],
            #     oids_results,
            #     sensor["sensor_details"]["expression"],
            #     sensor["sensor_details"]["output_path"],
            # )


        # log.info("Running job for account [{account_id}], IP [{ipv4}], nsensors: {n_sensors}, oids: {oids}".format(
        #     account_id=job_info["account_id"],
        #     ipv4=job_info["details"]["ipv4"],
        #     n_sensors=len(sensors),
        #     oids=["SNMP{} {}".format(o["fetch_method"].upper(), o["oid"]) for o in oids],
        # ))

    # @staticmethod
    # def send_results_to_grafolean(base_url, bot_token, account_id, entity_id, results, expression, output_path):
    #     url = '{}/api/accounts/{}/values/?b={}'.format(base_url, account_id, bot_token)
    #     values = []
    #     for ip in results:
    #         for ping_index, ping_time in enumerate(results[ip]):
    #             values.append({
    #                 'p': 'ping.{}.{}.success'.format(ip.replace('.', '_'), ping_index),
    #                 'v': 0 if ping_time is None else 1,
    #             })
    #             if ping_time is not None:
    #                 values.append({
    #                     'p': 'ping.{}.{}.rtt'.format(ip.replace('.', '_'), ping_index),
    #                     'v': ping_time,
    #                 })
    #     print("Sending results to Grafolean")
    #     r = requests.post(url, json=values)
    #     print(r.text)
    #     r.raise_for_status()



    def jobs(self):
        """
            Each entity (device) is a single job, no matter how many sensors it has. The reason is
            that when the intervals align, we can then issue a single SNMP Bulk GET/WALK.
        """
        for entity_info in self.fetch_job_configs('snmp'):
            intervals = list(set([sensor_info["interval"] for sensor_info in entity_info["sensors"]]))
            job_info = { **entity_info, "backend_url": self.backend_url, "bot_token": self.bot_token }
            yield intervals, SNMPCollector.do_snmp, job_info


if __name__ == "__main__":
    dotenv.load_dotenv()

    backend_url = os.environ.get('BACKEND_URL')
    bot_token = os.environ.get('BOT_TOKEN')
    if not backend_url or not bot_token:
        raise Exception("Please specify BACKEND_URL and BOT_TOKEN env vars.")

    c = SNMPCollector(backend_url, bot_token)
    c.execute()
