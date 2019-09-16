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

Docker is the easiest and currently the only officially supported way. Note that while instructions might (with possibly some modifications) work on other operating systems, Linux is assumed.

1) log in to Grafolean service (either https://grafolean.com/ or self-hosted), select an appropriate `Account` and create a new `Bot`. Make sure that selected protocol is `SNMP`. Copy the bot token.

2) save [docker-compose.yml](https://gitlab.com/grafolean/grafolean-collector-snmp/raw/master/docker-compose.yml) to a local file:
    ```
    $ mkdir ~/snmpcollector
    $ cd ~/snmpcollector
    $ wget https://gitlab.com/grafolean/grafolean-collector-snmp/raw/master/docker-compose.yml
    ```

3) edit `docker-compose.yml` and change:
    - mandatory: `BACKEND_URL` (set to the URL of Grafolean backend, for example `https://grafolean.com/api`),
    - mandatory: `BOT_TOKEN` (set to the bot token from step 1),
    - optional: `JOBS_REFRESH_INTERVAL` (interval in seconds at which the jobs definitions will be updated)
   Alternatively, you can also copy `.env.example` to `.env` and change settings there (leaving `docker-compose.yml` in original state).

4) run: `docker-compose up -d`

If you get no error, congratulations! Everything else is done from within the Grafolean UI. You can however check the status of container as usually by running `docker ps` and investigate logs by running `docker logs -f grafolean-collector-snmp`.

In case of error make sure that the user is allowed to run `docker` (that is, that it is in `docker` group) by running `docker ps`. Alternatively, container can be run using `sudo` (line 4 then reads `sudo docker-compose up -d`).

## Upgrade

Upgrading should be easy:

1) `$ docker-compose pull`
2) `$ docker-compose down`
3) `$ docker-compose up -d`

## Debugging

Container logs can be checked by running:
```
$ docker logs --since 5m -f grafolean-collector-snmp
```

## Building locally

If you wish to build the Docker image locally (for debugging or for development purposes), you can specify a custom docker-compose YAML file:
```
docker-compose -f docker-compose.dev.yml build
```

In this case `.env.example` can be copied to `.env` and all settings can be altered there, which helps us avoid commiting settings to the repository.

# Development

## Contributing

To contribute to this repository, CLA needs to be signed. Please open an issue about the problem you are facing before submitting a pull request.

## Issues

If you encounter any problems installing or running the software, please let us know in the [issues](https://gitlab.com/grafolean/grafolean-collector-snmp/issues). Please make an effort when describing the issue. If we can reproduce the problem, we can also fix it much faster.
