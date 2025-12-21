#!/usr/bin/env sh

docker exec -it acme_operador kamcmd htable.dump aor
docker exec -it acme_operador kamcmd htable.dump kpi
