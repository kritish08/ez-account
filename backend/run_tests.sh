#!/usr/bin/env bash
# Run the backend pytest suite inside the backend image against the local
# mongodb-atlas-local container (replica set — record_payment needs transactions).
#
#   ./run_tests.sh                    # whole suite
#   ./run_tests.sh tests/test_x.py    # one file
#   ./run_tests.sh -k some_test       # by name
set -euo pipefail
cd "$(dirname "$0")"

docker run --rm \
  -v "$PWD":/src -w /src \
  -e MONGO_URL="${MONGO_URL:-mongodb://host.docker.internal:27017/?directConnection=true}" \
  -e JWT_SECRET="test-jwt-secret-not-for-prod-0123456789" \
  -e MASTER_ENCRYPTION_KEY="0000000000000000000000000000000000000000000000000000000000000000" \
  -e CORS_ORIGINS="http://localhost" \
  ez-account-backend:latest python -m pytest "$@"
