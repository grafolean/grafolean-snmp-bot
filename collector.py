import requests
import logging


class Collector(object):
    def __init__(self, backend_url, bot_token):
        self.backend_url = backend_url
        self.bot_token = bot_token

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

                yield account_id, entity_info

