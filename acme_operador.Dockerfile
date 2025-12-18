FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \
    python3-dev \
    iproute2 \
    netbase \
    kamailio \
    kamailio-python3-modules \
    kamailio-extra-modules \
    && rm -rf /var/lib/apt/lists/*

ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libpython3.8.so.1.0

CMD ["/usr/sbin/kamailio", "-DD", "-E", "-f", "/etc/kamailio/kamailio.cfg"]
