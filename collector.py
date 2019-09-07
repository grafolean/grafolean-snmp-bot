import requests


class Collector(object):
    def __init__(self, backend_url, bot_token):
        self.backend_url = backend_url
        self.bot_token = bot_token

    def fetch_accounts_entities(self, protocol):
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
                # and hide all other protocols: (not strictly necessary, just cleaner)
                entity_info["protocols"] = {
                    protocol: entity_info["protocols"][protocol]
                }

                if not entity_info["protocols"][protocol]["sensors"]:
                    continue

                credential = None
                if entity_info["protocols"][protocol]["credential"]:
                    credential_id = entity_info["protocols"][protocol]["credential"]
                    r = requests.get('{}/accounts/{}/credentials/{}?b={}'.format(self.backend_url, account_id, credential_id, self.bot_token))
                    if r.status_code != 200:
                        raise Exception("Network error, got status {} while retrieving {}/accounts/{}/credentials/{}".format(r.status_code, self.backend_url, account_id, credential_id))
                    credential = r.json()

                sensors = []
                for sensor in entity_info["protocols"][protocol]["sensors"]:
                    r = requests.get('{}/accounts/{}/sensors/{}?b={}'.format(self.backend_url, account_id, sensor["sensor"], self.bot_token))
                    if r.status_code != 200:
                        raise Exception("Network error, got status {} while retrieving {}/accounts/{}/sensors/{}".format(r.status_code, self.backend_url, account_id, sensor["sensor"]))
                    sensors.append({
                        "sensor": r.json(),
                        "interval": sensor["interval"],
                    })
                entity_info["protocols"][protocol]["sensors"] = sensors

                yield account_id, entity_info, credential

