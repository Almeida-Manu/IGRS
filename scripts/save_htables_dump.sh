#!/usr/bin/env sh

mkdir -p "./data"
docker exec -it acme_operador kamcmd htable.dump aor > "./data/$(date +'%Y-%m-%dT%H:%M:%S.%3NZ')_aor_dump.txt"
docker exec -it acme_operador kamcmd htable.dump kpi > "./data/$(date +'%Y-%m-%dT%H:%M:%S.%3NZ')_kpi_dump.txt"
