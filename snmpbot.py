import os
import dotenv
import logging
import json
import time
from pytz import utc
from colors import color
import requests
import re

from easysnmp import Session, SNMPVariable
from mathjspy import MathJS
from slugify import slugify
import psycopg2

from grafoleancollector import Collector
from dbutils import get_db_cursor, DB_PREFIX, initial_wait_for_db, migrate_if_needed, db_disconnect, DBConnectionError


logging.basicConfig(format='%(asctime)s | %(levelname)s | %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S', level=logging.DEBUG)
logging.addLevelName(logging.DEBUG, color("DBG", 7))
logging.addLevelName(logging.INFO, "INF")
logging.addLevelName(logging.WARNING, color('WRN', fg='red'))
logging.addLevelName(logging.ERROR, color('ERR', bg='red'))
log = logging.getLogger("{}.{}".format(__name__, "base"))


class NoValueForOid(Exception):
    pass


class InvalidOutputPath(Exception):
    pass


OID_IF_DESCR = '1.3.6.1.2.1.2.2.1.2'
OID_IF_SPEED = '1.3.6.1.2.1.2.2.1.5'


def _get_previous_counter_value(counter_ident):
    with get_db_cursor() as c:
        try:
            c.execute(f'SELECT value, ts FROM {DB_PREFIX}bot_counters WHERE id = %s;', (counter_ident,))
            rec = c.fetchone()
            if rec is None:
                return None, None
        except psycopg2.ProgrammingError:
            log.exception(f'Error executing: SELECT value, ts FROM {DB_PREFIX}bot_counters WHERE id = %s; [{counter_ident}]')
            return None, None
        v, t = rec
        return int(v), float(t)


def _save_current_counter_value(new_value, now, counter_ident):
    with get_db_cursor() as c:
        c.execute(f"INSERT INTO {DB_PREFIX}bot_counters (id, value, ts) VALUES (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET value = %s, ts = %s;",
                (counter_ident, new_value, now, new_value, now))


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
        new_value = int(float(v.value))
        counter_ident = counter_ident_prefix + f'/{i}/{v.oid}/{v.oid_index}'
        try:
            old_value, t = _get_previous_counter_value(counter_ident)
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
        except DBConnectionError:
            log.error(f"Could not convert counter due to DB error: {counter_ident} / {new_value}")
    return new_results


def _construct_output_path(template, addressable_results, oid_index):
    # make sure that only valid characters are in the template:
    if not re.match(r'^([.0-9a-zA-Z_-]+|[{][^}]+[}])+$', template):
        raise InvalidOutputPath("Invalid output path template, could not parse")
    result_parts = []
    for between_dots in template.split('.'):
        OUTPUT_PATH_REGEX = r'([0-9a-zA-Z_-]+|[{][^}]+[}])'  # split parts with curly braces from those without
        for part in re.findall(OUTPUT_PATH_REGEX, between_dots):
            if part[0] != '{':
                result_parts.append(part)
                continue
            # expression parsing is currently a bit limited, we only replace {$1} to {$N} and {$index}
            if part[1] != '$':
                raise InvalidOutputPath("Only simple substitutions are currently supported (like 'abc.{$2}.{$index}.def') - was expecting '$' after '{'.")
            expression = part[2:-1]
            if expression == 'index':
                result_parts.append(oid_index)
            else:
                if not expression.isdigit():
                    raise InvalidOutputPath("Only simple substitutions are currently supported (like 'abc.{$2}.{$index}.def') - was expecting either 'index' or a number after '$'.")
                i = int(expression) - 1
                if not 0 <= i < len(addressable_results):
                    raise InvalidOutputPath(f"Could not create output path - the number after '$' should be between 1 and {len(addressable_results)} inclusive.")
                v = addressable_results[i][oid_index]
                clean_value = slugify(v.value, regex_pattern=r'[^0-9a-zA-Z_-]+', lowercase=False)
                result_parts.append(clean_value)

        result_parts.append('.')
    return ''.join(result_parts)[:-1]


def _apply_expression_to_results(snmp_results, methods, expression, output_path_template):
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
            known_output_paths = set()
            try:
                mjs = MathJS()
                for i, r in enumerate(addressable_results):
                    v = r.get(oid_index)
                    if v is None:  # oid index wasn't present
                        raise NoValueForOid()
                    if v.value is None:  # no value (probably the first time we're asking for a counter)
                        raise NoValueForOid()
                    var_name = f'${i + 1}'
                    if var_name in expression:  # not all values are used - some might be used by output_path
                        mjs.set(var_name, float(v.value))
                value = mjs.eval(expression)

                output_path = _construct_output_path(output_path_template, addressable_results, oid_index)
                if output_path in known_output_paths:
                    raise InvalidOutputPath("The same path was already constructed from a previous result, please include {$index} in the output path template, or make sure it is unique!")
                known_output_paths.add(output_path)
                result.append({
                    'p': output_path,
                    'v': value,
                })
            except NoValueForOid:
                log.warning(f'Missing value for oid index: {oid_index}')
            except InvalidOutputPath as ex:
                log.warning(f'Invalid output path for oid index [{oid_index}]: {str(ex)}')
        return result

    else:
        try:
            dummy_oid_index = '0'
            addressable_results = [{dummy_oid_index: v} for v in snmp_results]
            mjs = MathJS()
            for i, v in enumerate(snmp_results):
                if v.value is None:  # no value (probably the first time we're asking for a counter)
                    raise NoValueForOid()
                var_name = f'${i + 1}'
                if var_name in expression:  # not all values are used - some might be used by output_path
                    mjs.set(var_name, float(v.value))
            value = mjs.eval(expression)
            output_path = _construct_output_path(output_path_template, addressable_results, dummy_oid_index)
            return [
                {'p': output_path, 'v': value},
            ]
        except NoValueForOid:
            log.warning(f'Missing OID value (counter?)')
            return []


def send_results_to_grafolean(backend_url, bot_token, account_id, values):
    url = '{}/accounts/{}/values/?b={}'.format(backend_url, account_id, bot_token)

    if len(values) == 0:
        log.warning("No results available to be sent to Grafolean, skipping.")
        return

    log.info("Sending results to Grafolean")
    try:
        r = requests.post(url, json=values)
        r.raise_for_status()
        log.info("Results sent: {}".format(values))
    except:
        log.exception("Error sending data to Grafolean")


class SNMPBot(Collector):

    @staticmethod
    def _create_snmp_sesssion(job_info):
        # initialize SNMP session:
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
        return session

    @staticmethod
    def do_snmp(*args, **job_info):
        """
            {
                "backend_url": "...",
                "bot_token: "...",
                "account_id": 123,
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
                        "sensor_id": ...,
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
                        "sensor_id": ...,
                        "interval": 20
                    }
                ]
            }
        """
        log.info("Running job for account [{account_id}], IP [{ipv4}]".format(
            account_id=job_info["account_id"],
            ipv4=job_info["details"]["ipv4"],
        ))

        session = SNMPBot._create_snmp_sesssion(job_info)

        # filter out only those sensors that are supposed to run at this interval:
        affecting_intervals, = args
        activated_sensors = [s for s in job_info["sensors"] if s["interval"] in affecting_intervals]
        values = []
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
            new_values = _apply_expression_to_results(results_no_counters, methods, expression, output_path)
            values.extend(new_values)

        send_results_to_grafolean(job_info['backend_url'], job_info['bot_token'], job_info['account_id'], values)


    @staticmethod
    def update_if_entities(*args, **job_info):
        log.info("Running interfaces job for account [{account_id}], IP [{ipv4}]".format(
            account_id=job_info["account_id"],
            ipv4=job_info["details"]["ipv4"],
        ))

        session = SNMPBot._create_snmp_sesssion(job_info)

        parent_entity_id = job_info["entity_id"]
        account_id = job_info["account_id"]
        backend_url = job_info['backend_url']
        bot_token = job_info['bot_token']
        # fetch interfaces and update the interface entities:
        result_descr = session.walk(OID_IF_DESCR)
        result_speed = session.walk(OID_IF_SPEED)

        # make sure that indexes of results are aligned - we don't want to have incorrect data:
        if any([if_speed.oid_index != if_descr.oid_index for if_descr, if_speed in zip(result_descr, result_speed)]):
            log.warning(f"Out-of-order results for interface names on entity {parent_entity_id}, sorting not yet implemented, bailing out!")
            return

        # - get those entities on this account, which have this entity as their parent and filter them by type ('interface')
        requests_session = requests.Session()
        url = f'{backend_url}/accounts/{account_id}/entities/?parent={parent_entity_id}&entity_type=interface&b={bot_token}'
        r = requests_session.get(url)
        r.raise_for_status()
        # existing_entities = {x['details']['snmp_index']: (x['name'], x['details']['speed_bps'], x['id'],) for x in r.json()['list']}
        # Temporary, until we implement filtering in API:
        existing_entities = {x['details']['snmp_index']: (x['name'], x['details']['speed_bps'], x['id'],) for x in r.json()['list'] if x["entity_type"] == 'interface' and x["parent"] == parent_entity_id}

        for if_descr_snmpvalue, if_speed_snmpvalue in zip(result_descr, result_speed):
            oid_index = if_descr_snmpvalue.oid_index
            descr = if_descr_snmpvalue.value
            speed_bps = if_speed_snmpvalue.value
            # - for each new entity:
            #   - make sure it exists (if not, create it - POST)
            if oid_index not in existing_entities:
                log.debug(f"Entity with OID index {oid_index} is new, inserting.")
                url = f'{backend_url}/accounts/{account_id}/entities/?b={bot_token}'
                payload = {
                    "name": descr,
                    "entity_type": "interface",
                    "parent": parent_entity_id,
                    "details":{
                        "snmp_index": oid_index,
                        "speed_bps": speed_bps,
                    },
                }
                r = requests_session.post(url, json=payload)
                continue

            #   - make sure the description and speed are correct (if not, update them - PUT)
            existing_descr, existing_speed, existing_id = existing_entities[oid_index]
            if existing_descr != descr or existing_speed != speed_bps:
                log.debug(f"Entity with OID index {oid_index} changed data, updating.")
                url = f'{backend_url}/accounts/{account_id}/entities/{existing_id}/?b={bot_token}'
                payload = {
                    "name": descr,
                    "entity_type": "interface",
                    # "parent": parent_entity_id,  # changing entity parent is not possible
                    "details":{
                        "snmp_index": oid_index,
                        "speed_bps": speed_bps,
                    },
                }
                r = requests_session.put(url, json=payload)
                del existing_entities[oid_index]
                continue

            #   - mark it as processed
            log.debug(f"Entity with OID index {oid_index} didn't change.")
            del existing_entities[oid_index]

        # - for every existing entity that is not among the new ones, remove it (no point in keeping it - we don't keep old versions of enities data either)
        for oid_index in existing_entities:
            _, _, existing_id = existing_entities[oid_index]
            log.debug(f"Entity with OID index {oid_index} no longer exists, removing.")
            url = f'{backend_url}/accounts/{account_id}/entities/{existing_id}/?b={bot_token}'
            r = requests_session.delete(url)


    def jobs(self):
        """
            Each entity (device) is a single job, no matter how many sensors it has. The reason is
            that when the intervals align, we can then issue a single SNMP Bulk GET/WALK.
        """
        for entity_info in self.fetch_job_configs('snmp'):
            intervals = list(set([sensor_info["interval"] for sensor_info in entity_info["sensors"]]))
            job_info = { **entity_info, "backend_url": self.backend_url, "bot_token": self.bot_token }
            job_id = f'{entity_info["entity_id"]}'
            yield job_id, intervals, SNMPBot.do_snmp, job_info

            # We also collect interface data from each entity; the assumption is that everyone who wants
            # to use SNMP also wants to know about network interfaces.
            # Since `job_info` has all the necessary data, we simply pass it along:
            job_id = f'{entity_info["entity_id"]}-interfaces'
            yield job_id, [5*60], SNMPBot.update_if_entities, job_info


def wait_for_grafolean(backend_url):
    while True:
        url = '{}/status/info'.format(backend_url)
        log.info("Checking Grafolean status...")
        try:
            r = requests.get(url)
            r.raise_for_status()
            status_info = r.json()
            if status_info['db_migration_needed'] == False and status_info['user_exists'] == True:
                log.info("Grafolean backend is ready.")
                return
        except:
            pass
        log.info("Grafolean backend not available / initialized yet, waiting.")
        time.sleep(10)


if __name__ == "__main__":
    dotenv.load_dotenv()

    initial_wait_for_db()
    migrate_if_needed()
    db_disconnect()  # each worker should open their own connection pool

    backend_url = os.environ.get('BACKEND_URL')
    jobs_refresh_interval = int(os.environ.get('JOBS_REFRESH_INTERVAL', 120))

    if not backend_url:
        raise Exception("Please specify BACKEND_URL and BOT_TOKEN / BOT_TOKEN_FROM_FILE env vars.")

    wait_for_grafolean(backend_url)

    bot_token = os.environ.get('BOT_TOKEN')
    if not bot_token:
        # bot token can also be specified via contents of a file:
        bot_token_from_file = os.environ.get('BOT_TOKEN_FROM_FILE')
        if bot_token_from_file:
            with open(bot_token_from_file, 'rt') as f:
                bot_token = f.read()

    if not bot_token:
        raise Exception("Please specify BOT_TOKEN / BOT_TOKEN_FROM_FILE env var.")

    c = SNMPBot(backend_url, bot_token, jobs_refresh_interval)
    c.execute()
