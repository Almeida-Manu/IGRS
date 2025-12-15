FROM ubuntu:18.04

USER root

RUN apt-get update && apt-get install -y \
    python3 \
    python3-dev \
    iproute2 \
    kamailio 

#USER kamailio
