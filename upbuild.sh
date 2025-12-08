#!/usr/bin/env sh 

xhost +local:
docker-compose -f docker-compose.yaml up -d --build
