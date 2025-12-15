#!/usr/bin/env sh 

xhost +local:
docker-compose -f docker-compose-linux.yaml up -d --build
