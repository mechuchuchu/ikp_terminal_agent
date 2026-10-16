FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates coreutils curl wget \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir requests \
    && useradd --uid 10001 --create-home --shell /bin/sh agent

USER 10001:10001
WORKDIR /work
CMD ["sleep", "infinity"]

