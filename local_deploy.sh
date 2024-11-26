#!/bin/sh

docker build -t space-data-service:latest .
docker run -p 9988:8000 -it --rm space-data-service bash
