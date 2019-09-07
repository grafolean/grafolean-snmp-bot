import os


from collector import Collector


class SNMPCollector(Collector):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.init()

    def init(self):
        for account_id, entity_info, credential in self.fetch_accounts_entities('snmp'):
            # print(account_id, entity_info, credential)
            import json
            print(json.dumps(entity_info))

    def execute(self):
        pass

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    backend_url = os.environ.get('BACKEND_URL')
    bot_token = os.environ.get('BOT_TOKEN')
    if not backend_url or not bot_token:
        raise Exception("Please specify BACKEND_URL and BOT_TOKEN env vars.")

    c = SNMPCollector(backend_url, bot_token)
    c.execute()
