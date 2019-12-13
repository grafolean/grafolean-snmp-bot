FROM python:3.6-slim-stretch as python-requirements
COPY ./Pipfile ./Pipfile.lock /snmpbot/
WORKDIR /snmpbot
RUN \
    pip install pipenv && \
    pipenv lock -r > /requirements.txt

FROM python:3.6-slim-stretch as build-backend
COPY ./ /snmpbot/
WORKDIR /snmpbot
RUN \
    find ./ ! -name '*.py' -type f -exec rm '{}' ';' && \
    rm -rf tests/ .vscode/ .pytest_cache/ __pycache__/ && \
    python3.6 -m compileall -b ./ && \
    find ./ -name '*.py' -exec rm '{}' ';'


FROM python:3.6-slim-stretch
ARG VERSION
ARG VCS_REF
ARG BUILD_DATE
LABEL org.label-schema.vendor="Grafolean" \
      org.label-schema.url="https://grafolean.com/" \
      org.label-schema.name="Grafolean SNMP bot" \
      org.label-schema.description="SNMP bot for Grafolean" \
      org.label-schema.version=$VERSION \
      org.label-schema.vcs-url="https://github.com/grafolean/grafolean-snmp-bot/" \
      org.label-schema.vcs-ref=$VCS_REF \
      org.label-schema.build-date=$BUILD_DATE \
      org.label-schema.docker.schema-version="1.0"
COPY --from=python-requirements /requirements.txt /requirements.txt
RUN \
    apt-get update && \
    apt-get install --no-install-recommends -q -y libsnmp-dev build-essential git && \
    pip install --no-cache-dir -r /requirements.txt && \
    apt-get purge -y build-essential && \
    apt-get clean autoclean && \
    apt-get autoremove --yes && \
    rm -rf /var/lib/{apt,dpkg,cache,log}/ && \
    echo "alias l='ls -altr'" >> /root/.bashrc
COPY --from=build-backend /snmpbot/ /snmpbot/
WORKDIR /snmpbot
# check for "fail" file and if it exists, remove it and fail the check:
HEALTHCHECK --interval=10s --retries=1 CMD /bin/bash -c "[ ! -f /tmp/fail_health_check ] || ( rm /tmp/fail_health_check && exit 1 )"
CMD ["python", "-m", "snmpbot"]
