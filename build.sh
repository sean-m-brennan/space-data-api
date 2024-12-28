#!/bin/sh

if [ ! -e app/api/users.json ]; then
  echo "ERROR: users.json required"
  exit 1
fi

# Generate spice data
PYTHONPATH=app python -m api $@
