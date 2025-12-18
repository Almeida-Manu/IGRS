#!/usr/bin/env sh

mkdir -p "./data"
docker exec -it acme_operador /usr/sbin/kamcmd ul.dump > "./data/$(date +'%Y-%m-%dT%H:%M:%S.%3NZ')_dump.txt"
