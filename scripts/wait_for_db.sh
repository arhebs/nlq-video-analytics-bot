#!/usr/bin/env bash
set -euo pipefail

service_name="${1:-postgres}"
retries="${2:-30}"

for ((i=1; i<=retries; i++)); do
  if docker compose exec -T "$service_name" pg_isready -U postgres -d video_analytics >/dev/null 2>&1; then
    exit 0
  fi
  sleep 1
done

echo "Postgres did not become ready in time" >&2
exit 1

