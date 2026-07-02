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
