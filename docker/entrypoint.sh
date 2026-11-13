#!/bin/sh
# Rebuild derived memory from source assets, then serve.
#
# Startup fails loudly when the profile is unset, when indexing fails, or when
# Wren cannot resolve the selected profile. The server never listens on a stale
# or partially rebuilt index.
set -eu

: "${WREN_PROFILE:?Set WREN_PROFILE (jaffle-dev, clickhouse-staging, clickhouse-prod)}"

/app/.venv/bin/python /app/docker/initialize_memory.py

exec /app/.venv/bin/wren serve mcp \
    --project /app/project \
    --profile "$WREN_PROFILE" \
    --transport http \
    --host 0.0.0.0 \
    --port 8080
