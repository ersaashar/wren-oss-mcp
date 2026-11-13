# Manual deployment

DEV uses the Jaffle image. Staging and production have separate ClickHouse profiles but share one reserved semantic project under `projects/clickhouse-mart/`. The project is not yet buildable: its manifest and real schema are intentionally absent. Do not deploy the example image digest or credentials.

## ClickHouse handoff

Before building the ClickHouse image, obtain:

- Table and column names, types, primary and foreign keys, and catalog/schema mapping.
- Approved relationships, business rules, and reviewed NL-SQL examples.
- A development endpoint, CA, port, and least-privileged read-only account for validating the model.
- Staging and production reachability, trusted CA configuration, authenticated proxy and client access requirements.
- Container registry access and deployment hosts.

Grant each ClickHouse account only the required SELECT permissions. Wren strict mode supplements, but does not replace, database authorization.

## Populate the ClickHouse project

Use one semantic project for both environments when their approved schemas and semantics match. The image contains this project; the selected runtime profile supplies the environment-specific connection. The reserved directories are:

```text
projects/clickhouse-mart/
  models/             # one directory per semantic model
  views/              # optional semantic views
  knowledge/rules/    # reviewed business rules
  knowledge/sql/      # reviewed NL-to-SQL examples
```

The `.gitkeep` files only preserve directories in Git. They are not models. From the repository root, initialize the project when the schema is available:

```bash
uv sync --locked
uv run --frozen wren context init --path projects/clickhouse-mart --empty
```

This generates `wren_project.yml`, `relationships.yml`, and starter knowledge files. Edit `projects/clickhouse-mart/wren_project.yml`: set `name: clickhouse-mart` and `data_source: clickhouse`; keep `schema_version: 5`, `catalog: wren`, and `schema: public`. Those catalog and schema values are the Wren namespace, not the ClickHouse database. Do not add an environment-specific `profile` to the project. Review or remove generated starter guidance before committing; do not run installers suggested by the CLI without reviewing them.

Create a directory under `models/` for each approved model and add `metadata.yml`. Use the existing `projects/jaffle-wren/models/orders/metadata.yml` as a format reference, not as a ClickHouse schema. Replace its `name`, `table_reference`, `primary_key`, columns, types, nullability, and descriptions with the real ClickHouse table details. Set `table_reference` catalog and schema according to the actual connector and database layout, and test the mapping against your endpoint. Define only verified joins in `relationships.yml`. Add approved business rules as Markdown under `knowledge/rules/` and approved examples under `knowledge/sql/`; see [knowledge and memory](knowledge-and-memory.md#adding-a-curated-nlsql-example) for their frontmatter format. Empty `knowledge/sql/` is valid.

Validate and compile the real project:

```bash
uv run --frozen wren context validate --path projects/clickhouse-mart
uv run --frozen wren context build --path projects/clickhouse-mart
```

Review the generated `target/mdl.json` and test semantic queries against an authorized non-production ClickHouse endpoint before building the image. These local validation commands do not prove database connectivity, TLS, permissions, or query results. The generated `target/` and `.wren/` are ignored; commit the reviewed source files only.

## Fill staging and production settings

The committed registries `config/profiles/staging.yml` and `config/profiles/prod.yml` already select `clickhouse-staging` and `clickhouse-prod`. Both use TLS and resolve `CH_HOST`, `CH_PORT`, `CH_DATABASE`, `CH_USER`, and `CH_PASSWORD` from their respective environment files. Do not edit those registries to embed credentials.

On each deployment host, create the corresponding ignored file only if it does not already exist:

```bash
# Staging host
cp .env.staging.example .env.staging
# Production host
cp .env.prod.example .env.prod
```

Edit the relevant file with the real endpoint, port, database and read-only account. Set `WREN_IMAGE` to the actual pushed image digest. Never copy staging credentials into production or commit either env file. Secure the files according to the host's access controls. Staging and production need compatible semantic schemas; environment-specific physical differences require explicit modeling and verification rather than changing the promoted image.

## Secrets and profiles

Copy `.env.staging.example` and `.env.prod.example` to `.env.staging` and `.env.prod` on the appropriate hosts. Restrict file access to the deployment operator. Replace every placeholder. Never commit these files or print their contents in logs. Compose interpolates `WREN_ENV`, `WREN_PROFILE`, and `WREN_IMAGE`; Wren resolves `${CH_*}` in the mounted profile at startup. `secure: true` requires TLS to ClickHouse and a trusted server certificate; install the appropriate CA in the image or deployment trust store before use.

The base Compose file publishes no host port. Each `-p` name isolates its network and memory volume. The profile bind is read-only. TCP health checks indicate process liveness only; database connectivity is lazy and requires a real MCP query to verify.

## Build and push images

Run from the repository root. Image tags below are examples; replace `<release>` with an immutable release identifier. Jaffle can be built now; ClickHouse is conditional on the handoff above. Both builds need access to the pinned Python and uv images, PyPI, and Hugging Face model files.

```bash
docker build -f docker/Dockerfile --build-arg WREN_PROJECT=jaffle-wren \
  -t ghcr.io/ibukansaya/wren-jaffle:<release> .
docker push ghcr.io/ibukansaya/wren-jaffle:<release>

# Only after the real ClickHouse project has been added and validated:
docker build -f docker/Dockerfile --build-arg WREN_PROJECT=clickhouse-mart \
  -t ghcr.io/ibukansaya/wren-clickhouse:<release> .
docker push ghcr.io/ibukansaya/wren-clickhouse:<release>
```

Record the pushed image's registry digest from the push output or inspect the registry manifest:

```bash
docker buildx imagetools inspect ghcr.io/ibukansaya/wren-clickhouse:<release>
```

Set `WREN_IMAGE=ghcr.io/ibukansaya/wren-clickhouse@sha256:<actual-digest>` in the protected staging env file. Replace the entire placeholder with the actual 64-hex digest. Do not use a tag for promotion.

## Staging

After the ClickHouse handoff and proxy are in place:

```bash
docker compose -p wren-staging --env-file .env.staging -f deploy/compose.yml pull
docker compose -p wren-staging --env-file .env.staging -f deploy/compose.yml up -d --wait --wait-timeout 180
docker compose -p wren-staging --env-file .env.staging -f deploy/compose.yml logs --tail 100 wren-mcp
```

Test authentication, connectivity, allowed semantic queries, forbidden access, and curated memory using an authorized MCP client through the actual proxy. The Jaffle smoke client asserts fixture-specific results and is not a ClickHouse acceptance test. Record the digest and test results.

## Promotion and rollback

Set production `WREN_IMAGE` to the **same digest tested in staging**, not a rebuilt image or a movable tag. Confirm the production profile, credentials, network and proxy independently.

```bash
docker compose -p wren-prod --env-file .env.prod -f deploy/compose.yml pull
docker compose -p wren-prod --env-file .env.prod -f deploy/compose.yml up -d --wait --wait-timeout 180
```

For rollback, set `WREN_IMAGE` in `.env.prod` to the previous tested digest, then repeat the same `pull` and `up` commands. Keep the previous digest in the deployment record. The persistent memory volume is reconciled to the selected image on startup; validate the rollback with an authorized MCP query.

## Access and proxy

Wren 0.17.1 has no built-in authentication. Do not publicly publish port 8080. DEV publishes only host loopback: host clients use `http://127.0.0.1:8080/mcp`. In a different container, `localhost` refers to that client container, not Wren.

Use an authenticated TLS reverse proxy on a private network for remote or container clients. Wren with MCP 1.30.0 enforces Host and Origin protections even when bound to `0.0.0.0`; a direct request using a container hostname is not generally accepted. Configure the proxy to forward upstream `Host: 127.0.0.1:8080`. Validate browser `Origin` against an explicit proxy allowlist before normalizing or removing it upstream. Never disable DNS-rebinding protection to make networking work. Proxy, browser, and AnythingLLM integration have not been tested here.

## Memory operations

Compose project names produce separate volumes (`wren-dev_wren_memory`, `wren-staging_wren_memory`, `wren-prod_wren_memory`). Do not share them across environments. `down` retains volumes; `down -v` deletes them. Startup replaces schema vectors and reconciles Markdown-backed examples; restart to reindex after deploying an image. See [knowledge and memory](knowledge-and-memory.md).

Back up a stopped deployment's volume using your approved volume backup procedure, encrypt and protect the backup, and test restoration in isolation. Memory is derived from versioned image contents, but may contain legacy non-Markdown rows; preserve backups according to the environment's retention policy. Inspect startup errors with `docker compose ... logs wren-mcp`; failed initialization prevents the server from listening.
