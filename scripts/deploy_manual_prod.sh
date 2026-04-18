#!/usr/bin/env bash
set -euo pipefail

# Manual production deployment using local docker-compose.yml.
# Expected workflow:
# 1) Merge into Prod branch on GitHub.
# 2) Run this script on the target server in the repo directory.

BRANCH="${1:-Prod}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8001/health}"

echo "[deploy] Updating repository branch: ${BRANCH}"
git fetch origin
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}"

echo "[deploy] Building and starting container via docker compose"
docker compose down --remove-orphans
docker compose up -d --build

echo "[deploy] Waiting for health endpoint: ${HEALTH_URL}"
for i in $(seq 1 45); do
  if curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "[deploy] Service is healthy"
    docker compose ps
    exit 0
  fi
  sleep 2
done

echo "[deploy] Healthcheck failed. Last logs:"
docker compose logs --tail=200 daqs || true
exit 1
