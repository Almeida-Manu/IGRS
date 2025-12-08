FROM ghcr.io/kamailio/kamailio:6.0.3-focal

USER root

RUN apt-get update && apt-get install -y \
    python3 \
    python3-dev \
    kamailio-postgres-modules \
    kamailio-python3-modules \
    && rm -rf /var/lib/apt/lists/*

USER kamailio
