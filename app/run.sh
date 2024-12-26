#!/bin/sh

args="--ssl-keyfile ./key.pem --ssl-certfile ./cert.pem"
for arg in "$@"; do
  if [ "$arg" = "--not-secure" ]; then
    args=""
  fi
done

uvicorn main:app --host 0.0.0.0 --port 8000 $args
