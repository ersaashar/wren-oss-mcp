# Development

The DEV deployment runs the Jaffle Shop semantic project over a bundled DuckDB
fixture. It is fully self-contained: after `docker compose up` the service needs
no network access for dependencies, model weights, or data.

## Prerequisites

- **Docker Desktop** with the Linux engine running. Verify with
  `docker info --format '{{.ServerVersion}}'`; a CLI that exists while the engine
  is stopped is not a working runtime.
- **uv** (0.11 or newer) for host-side validation and the smoke client.
- **Git Bash** on Windows or any POSIX shell on Linux. Commands below are
  written to work in both.

The container image installs Python and every dependency itself, so no local
Python version is required beyond what `uv` manages for host checks.

## Provenance of the imported assets

The DEV semantic project was imported from the previous `pg_wrenai` repository
and is now independent of it. Nothing is copied at runtime.

|Path|Origin|
|---|---|
|`projects/jaffle-wren/models/{orders,customers}/metadata.yml`|`pg_wrenai/jaffle-wren/models/`|
|`projects/jaffle-wren/relationships.yml`|`pg_wrenai/jaffle-wren/relationships.yml`|
|`projects/jaffle-wren/knowledge/rules/{conventions,jaffle_shop}.md`|`pg_wrenai/jaffle-wren/knowledge/rules/`|
|`projects/jaffle-wren/knowledge/sql/order-count.md`|New: first curated NL→SQL example|
|`data/jaffle_shop.duckdb`|`pg_wrenai/jaffle_shop_duckdb/jaffle_shop.duckdb` (dbt-labs Jaffle Shop)|
|`data/JAFFLE_LICENSE`|Apache-2.0 license of that fixture|

Deliberately **not** imported: the source project's `target/`, `.wren/`,
`AGENTS.md`, nested `.gitignore`, `knowledge/rules/general.md` (placeholder
text only), dbt tooling, seeds, virtual environment, and application scaffolding.

### Fixture identity

|Property|Expected|
|---|---|
|SHA-256|`290fc8e5cf4e0f8965f1e1c6a98a439e1fcd44396cd99b39a759398c36e4e67a`|
|Size|1585152 bytes|
|Customers|100|
|Orders|99|
|Joined orders|99|
|Orphan orders|0|
|Total order value|AUD 1672.00|

The fixture filename matters: both model definitions reference catalog
`jaffle_shop` and schema `main`. Preserve the filename: DuckDB derives the
catalog name from it.

## Quickstart

```bash
cp .env.dev.example .env.dev

docker compose -p wren-dev --env-file .env.dev \
  -f deploy/compose.yml -f deploy/compose.dev.yml up -d --build --wait --wait-timeout 180

uv run --frozen python scripts/smoke_mcp.py
```

The default host endpoint is `http://127.0.0.1:8080/mcp`. Set `WREN_PORT` in
`.env.dev` to select another host port, then recreate the container. The
container continues to listen on 8080. For example, with `WREN_PORT=18080`:

```bash
uv run --frozen python scripts/smoke_mcp.py --url http://127.0.0.1:18080/mcp
```

## Run directly with uv and Wren CLI

This host-only DEV workflow does not require Docker. It uses a separate registry
under `.wren/host` and the original fixture in `data/`; the container profile
points to `/app/data` and cannot be reused on the host. The first initialization
downloads the ONNX model into the host Hugging Face cache and needs network
access. Host memory is stored in `projects/jaffle-wren/.wren/memory`, separate
from the Docker volume.

With `just` installed, run `just dev` from the repository root. The recipe
syncs dependencies, validates and builds the project, initializes memory, and
starts Wren in the foreground. It reads `WREN_PORT` from `.env.dev`, defaulting
to 8080; a `WREN_PORT` environment variable overrides the file. Stop it with
Ctrl+C. Docker and the host server cannot use the same port simultaneously.

Alternatively, run the steps manually:

In Git Bash on Windows or a POSIX shell on Linux, from the repository root:

```bash
uv sync --locked
uv run --frozen wren context validate --path projects/jaffle-wren
uv run --frozen wren context build --path projects/jaffle-wren

# Strip Windows CR from the captured Python output.
export WREN_HOME="$(uv run --frozen python -c 'from pathlib import Path; print((Path.cwd() / ".wren" / "host").resolve())' | tr -d '\r')"
export WREN_MEMORY_BACKEND=lancedb
export WREN_EMBEDDING_BACKEND=onnx
export WREN_EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2

uv run --frozen python - <<'PY'
import os
import shutil
import sys
from pathlib import Path
import yaml

home = Path(os.environ["WREN_HOME"])
home.mkdir(parents=True, exist_ok=True)
shutil.copyfile("config/wren-config.json", home / "config.json")
profile = {
    "active": "jaffle-host",
    "profiles": {
        "jaffle-host": {
            "datasource": "duckdb",
            "url": str(Path("data").resolve()),
            "format": "duckdb",
        }
    },
}
(home / "profiles.yml").write_text(yaml.safe_dump(profile), encoding="utf-8")
sys.path.insert(0, "docker")
from initialize_memory import initialize_memory
initialize_memory(Path("projects/jaffle-wren"))
PY

uv run --frozen wren serve mcp --project projects/jaffle-wren \
  --profile jaffle-host --transport http --host 127.0.0.1 --port 18081
```

Keep that terminal open. In another terminal:

```bash
uv run --frozen python scripts/smoke_mcp.py --url http://127.0.0.1:18081/mcp
```

Choose an unused `--port` if 18081 is occupied. `WREN_PORT` in `.env.dev` is
the Compose host-port setting; the direct CLI uses its own `--port` argument.
Rebuild and reinitialize after semantic or knowledge edits. Stop the host server
with Ctrl+C. The host server has no authentication; keep it on loopback.

## Host-side checks

These validate the semantic sources with the same locked environment the image
uses. They do not need Docker and they do not start a server.

```bash
uv sync --locked
uv run --frozen wren context validate --path projects/jaffle-wren
uv run --frozen wren context build --path projects/jaffle-wren
```

Expected output: `Valid — 2 models, 0 views, 1 relationships.` and
`Built: 2 models, 0 views`. The compiled
`projects/jaffle-wren/target/mdl.json` is a build artefact and is not committed.

### Verify the fixture bytes

```bash
sha256sum data/jaffle_shop.duckdb          # Linux / Git Bash
stat -c '%s' data/jaffle_shop.duckdb       # size in bytes
```

### Verify the fixture aggregates

```bash
uv run --frozen python - <<'PY'
import duckdb
con = duckdb.connect("data/jaffle_shop.duckdb", read_only=True)
for sql in (
    "SELECT COUNT(*) FROM jaffle_shop.main.customers",
    "SELECT COUNT(*) FROM jaffle_shop.main.orders",
    "SELECT ROUND(SUM(amount), 2) FROM jaffle_shop.main.orders",
    "SELECT COUNT(*) FROM jaffle_shop.main.orders o "
    "JOIN jaffle_shop.main.customers c ON o.customer_id = c.customer_id",
):
    print(sql, con.execute(sql).fetchall())
con.close()
PY
```

### Verify the curated Markdown parses

```bash
uv run --frozen python - <<'PY'
from pathlib import Path
from wren.memory.markdown import load_query_pairs

for pair in load_query_pairs(Path("projects/jaffle-wren")):
    print(pair["nl"])
    print(pair["sql"])
PY
```

This uses Wren's own parser, so a passing result means the file is genuinely
indexable rather than merely well-formed YAML.

## Lifecycle commands

Run all of them with the same `-p`, `--env-file` and `-f` flags for the target
environment.

|Goal|Command|
|---|---|
|Start or update|`docker compose -p wren-dev --env-file .env.dev -f deploy/compose.yml -f deploy/compose.dev.yml up -d --build --wait --wait-timeout 180`|
|Logs|`docker compose -p wren-dev --env-file .env.dev -f deploy/compose.yml -f deploy/compose.dev.yml logs -f wren-mcp`|
|Stop, keep memory|`docker compose -p wren-dev --env-file .env.dev -f deploy/compose.yml -f deploy/compose.dev.yml down`|
|Restart after source edits|rebuild with `up -d --build`; the memory volume is kept|
|Discard derived memory too|add `-v` to `down`|

`--force-recreate` restarts the container without touching the memory volume,
which is how the startup reconciliation path is exercised:

```bash
docker compose -p wren-dev --env-file .env.dev \
  -f deploy/compose.yml -f deploy/compose.dev.yml \
  up -d --force-recreate --wait --wait-timeout 180
```

Each container start re-runs `docker/initialize_memory.py`.

## The smoke client

`scripts/smoke_mcp.py` is a real MCP client, not an HTTP ping. It opens a
streamable-HTTP session against `--url` (default
`http://127.0.0.1:8080/mcp`) and asserts:

- the read-only tool surface exists and `store_query` does not;
- `list_models` and `get_mdl` report `customers`, `orders` and the
  `orders_customers` relationship;
- `run_sql` returns 100 customers, 99 orders, AUD 1672.00 revenue and 99 joined
  orders;
- `get_instructions` carries the imported AUD and `raw_*` rules;
- `get_context` returns both models for `customer orders`;
- `recall_queries` returns the curated pair, which proves the ONNX embedding path
  works offline;
- `list_stored_queries` contains the curated pair and no `source:seed` rows;
- a direct `store_query` call is rejected;
- `DELETE FROM orders` and a read of the non-MDL `jaffle_shop.main.raw_orders`
  table are both rejected, and the order count is still 99 afterwards.

It prints one line on success and exits nonzero on the first failed assertion.
The same script is copied into the image, so it can also be run from inside a
container against a reachable endpoint.

## Troubleshooting

|Symptom|Cause|
|---|---|
|`Set WREN_IMAGE` / `Set WREN_ENV` / `Set WREN_PROFILE`|The matching variable is missing from the `--env-file` file.|
|`no such file or directory: .../profiles.yml`|`WREN_ENV` does not match a file in `config/profiles/`.|
|`profile 'X' not found`|`WREN_PROFILE` is not a key under `profiles:` in the mounted registry.|
|`Profile references ${...} but it is not set`|A `${CH_*}` placeholder is unresolved; the variable must come from the env file.|
|Container restarts repeatedly|Read the logs: initialization or profile resolution failed. Startup is fail-closed by design.|
|Smoke client connection refused|The container is not yet listening, or the port is not published (only the DEV overlay publishes one).|
|Port 8080 already allocated|Set `WREN_PORT` in `.env.dev` to an available port and pass it to the smoke client.|
|Docker predefined address pools exhausted|Coordinate with the Docker administrator to free unused networks or configure a non-overlapping address pool. Do not remove other projects' networks blindly.|

## Boundaries

- Host and Docker deployments use different profile registries and memory stores.
- See [deployment.md](deployment.md) for staging and production prerequisites.
