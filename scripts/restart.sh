#!/usr/bin/env sh 

docker-compose -f docker-compose.yaml down -v
xhost -local:

xhost +local:
docker-compose -f docker-compose.yaml up -d --build
