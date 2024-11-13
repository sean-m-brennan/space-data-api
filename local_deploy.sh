#!/bin/sh

docker build -t spice-service:latest .
docker run -p 9988:8000 -it --rm spice-service bash
