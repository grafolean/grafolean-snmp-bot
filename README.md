# About Grafolean SNMP Collector

This package is a SNMP Collector for Grafolean, an easy to use generic monitoring system.

Once installed, all the configuration of SNMP sensors is done through Grafolean's web-based user interface. Depending on permissions,
a single SNMP Collector instance can be fetching data for multiple accounts and entities. The fetching intervals can be specified with
up to a second precision.

Under the hood it uses [net-snmp](http://net-snmp.sourceforge.net/) (via [easysnmp](https://easysnmp.readthedocs.io)), which means
it should be compatible with any device that can respond to requests by `snmpget` and `snmpwalk`.

Requirements:
- the devices that should be queried via SNMP must be accessible *from the container* (make sure SNMP Collector is installed in correct network and that there are no firewalls in between)
- Grafolean must be accessible via HTTP(S)

Current limitations:
- does not yet support out-of-order SNMP WALK responses
- does not yet limit the maximum number of retrieved OIDs when doing SNMP WALK
- BULK GET/WALK is not supported yet

# License

License is Commons Clause license (on top of Apache 2.0) - source is available, you can use it for free (commercially too), modify and
share, but you can't sell it. See [LICENSE.md](https://gitlab.com/grafolean/grafolean-collector-snmp/blob/master/LICENSE.md) for details.

If in doubt, please [open an issue](https://gitlab.com/grafolean/grafolean-collector-snmp/issues) to get further clarification.

# Install (docker / docker-compose)

This is the easiest and currently the only officially supported way. However other installation methods should be straightforward by studying `Dockerfile`.

1) log in to Grafolean service (either https://grafolean.com/ or self-hosted), select an appropriate `Account` and create a new `Bot`. Make sure that selected protocol is `SNMP`. Copy the bot token.
2) save [docker-compose.yml](https://gitlab.com/grafolean/grafolean-collector-snmp/raw/master/docker-compose.yml) to a local file
3) edit `docker-compose.yml` and change:
    - mandatory: `BACKEND_URL` (set to the URL of Grafolean backend, for example `https://grafolean.com/api`),
    - mandatory: `BOT_TOKEN` (set to the bot token from step 1),
    - optional: `JOBS_REFRESH_INTERVAL` (interval in seconds at which the jobs definitions will be updated)
3) run: `docker-compose up -d`

## Upgrade

1) `docker-compose pull`
2) `docker-compose down && docker-compose up -d`

## Debugging

Container logs can be checked by running:
```
$ docker logs grafolean-collector-snmp
```

# Development

## Contributing

To contribute to this repository, CLA needs to be signed. Please open an issue about the problem you are facing before submitting a pull request.

## Issues

If you encounter any problems installing or running the software, please let us know in the [issues](https://gitlab.com/grafolean/grafolean-collector-snmp/issues). If possible, please make sure to describe the issue in a way that will allow us to reproduce it.
