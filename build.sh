#!/bin/sh
#  Copyright 2024 Sean M. Brennan and contributors
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

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
