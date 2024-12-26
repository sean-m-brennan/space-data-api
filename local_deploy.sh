#!/bin/sh

if [ ! -e app/api/users.json ]; then
  echo "ERROR: users.json required"
  exit 1
fi
if [ ! -e app/cert.pem ] || [ ! -e app/key.pem ]; then
  echo "ERROR: cert.pem and key.pem required"
  exit 1
fi
debug=false
for arg in "$@"; do
  if [ "$arg" = "--debug" ]; then
    debug=true
  fi
done

docker build -t space-data-service:latest .

if $debug; then
  docker run -p 9988:8000 -it --rm space-data-service bash
else
  docker run -p 9988:8000 -d --rm space-data-service
  # when finished: `docker container stop space-data-service`
fi
