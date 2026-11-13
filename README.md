# Standalone Wren OSS MCP

A standalone Wren AI OSS MCP service. The DEV semantic project uses the imported Jaffle Shop models and a bundled DuckDB fixture. It does not depend on a chatbot or the original repository.

Staging and production have separate ClickHouse profiles and a shared reserved semantic-project structure. Populate it using the [ClickHouse setup guide](docs/deployment.md#populate-the-clickhouse-project) after the schema and access handoff; the ClickHouse image and deployments are not yet available.

## Prerequisites

- Docker Desktop with its Linux engine running.
- `uv` and Git Bash on Windows, or a POSIX shell on Linux.
- Network access during image builds for container images, Python dependencies and ONNX model assets.
- `just` to use the Docker-free `just dev` recipe.

## DEV quickstart

For a host-only server, run `just dev`. It reads `WREN_PORT` from `.env.dev`
(default 8080) and runs in the foreground. Stop it with Ctrl+C. The Docker
alternative follows.

From the repository root:

```bash
cp .env.dev.example .env.dev
uv sync --locked

docker compose -p wren-dev --env-file .env.dev \
  -f deploy/compose.yml -f deploy/compose.dev.yml \
  up -d --build --wait --wait-timeout 180

uv run --frozen python scripts/smoke_mcp.py --url http://127.0.0.1:8080/mcp
```

The default host MCP endpoint is `http://127.0.0.1:8080/mcp`. To change it, set `WREN_PORT` in `.env.dev`, recreate the container, and pass the chosen port to the smoke client's `--url`. Only DEV publishes a host port, bound to loopback. Wren has no built-in authentication; remote deployments require an authenticated proxy.

## Guides

- [Architecture](docs/architecture.md): image variants, profiles, and memory.
- [Development](docs/development.md): provenance, validation, and DEV lifecycle.
- [Knowledge and memory](docs/knowledge-and-memory.md): Markdown curation and startup indexing.
- [Deployment](docs/deployment.md): ClickHouse prerequisites, image promotion, security, and rollback.

`uv` owns Python dependencies, the directories under `projects/` own semantic assets, and Compose selects container environments. For a Docker-free DEV server, use the [host uv and Wren CLI workflow](docs/development.md#run-directly-with-uv-and-wren-cli).
