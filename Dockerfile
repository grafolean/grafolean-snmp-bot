FROM python:3.6-slim-stretch as python-requirements
COPY ./Pipfile ./Pipfile.lock /snmpcollector/
WORKDIR /snmpcollector
RUN \
    pip install pipenv && \
    pipenv lock -r > /requirements.txt

FROM python:3.6-slim-stretch as build-backend
COPY ./ /snmpcollector/
WORKDIR /snmpcollector
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
      org.label-schema.name="Grafolean SNMP Collector" \
      org.label-schema.description="SNMP collector for Grafolean" \
      org.label-schema.version=$VERSION \
      org.label-schema.vcs-url="https://gitlab.com/grafolean/grafolean-collector-snmp/" \
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
COPY --from=build-backend /snmpcollector/ /snmpcollector/
WORKDIR /snmpcollector
CMD ["python", "-m", "snmpcollector"]
