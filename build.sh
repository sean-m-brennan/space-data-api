#!/bin/sh

if [ ! -e app/api/users.json ]; then
  echo "ERROR: users.json required"
  exit 1
fi

# Generate swagger info from running server
cd app
./run.sh --not-secure &
pid=$!
sleep 3
cd ..
wget http://localhost:8000/openapi.json -O swagger.json
npm run generate-client
kill $(pgrep -P $pid)

# Generate spice data
PYTHONPATH=app python -m api $@
