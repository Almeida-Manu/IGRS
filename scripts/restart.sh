#!/usr/bin/env sh 

docker-compose -f docker-compose-linux.yaml down -v
xhost -local:

xhost +local:
docker-compose -f docker-compose-linux.yaml up -d --build
