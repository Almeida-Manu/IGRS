FROM ubuntu:20.04

RUN apt-get update && apt-get install -y \
    python3 \
    python3-dev \
    iproute2 \
    kamailio \
    kamailio-extra-modules \
    && rm -rf /var/lib/apt/lists/*
