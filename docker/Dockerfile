# One selected-project image: the dependency environment is shared, the semantic
# project and its data are selected at build time.
#
#   docker build -f docker/Dockerfile --build-arg WREN_PROJECT=jaffle-wren .
#
# Base images are pinned by manifest-list digest so a rebuild cannot silently
# change the Python family or the uv release.

ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ARG UV_IMAGE=ghcr.io/astral-sh/uv@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490

FROM ${UV_IMAGE} AS uv

# ── Dependency environment ─────────────────────────────────────────────────
FROM ${PYTHON_IMAGE} AS builder

ARG WREN_PROJECT=jaffle-wren

ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

COPY --from=uv /uv /uvx /bin/

RUN apt-get update \
    && apt-get install --no-install-recommends --yes ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies only: locked, no dev group, project itself is not a package.
COPY .python-version pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

ENV PATH=/app/.venv/bin:$PATH \
    HF_HOME=/opt/wren-model-cache \
    WREN_MEMORY_BACKEND=lancedb \
    WREN_EMBEDDING_BACKEND=onnx \
    WREN_EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2

# Bake the embedding model with Wren's own loader so the runtime needs no network.
RUN python -c "from wren.memory.embeddings import get_embedding_function, warm_up; assert warm_up(get_embedding_function()) == 384"

# Fail the build when the selected semantic project is absent or invalid.
COPY projects/${WREN_PROJECT}/ /app/project/
RUN wren context validate --path /app/project \
    && wren context build --path /app/project

# Fixture data is staged per project so a ClickHouse image carries no Jaffle bytes.
COPY data/ /tmp/data/
RUN mkdir -p /app/data \
    && if [ "${WREN_PROJECT}" = "jaffle-wren" ]; then \
         cp /tmp/data/jaffle_shop.duckdb /tmp/data/JAFFLE_LICENSE /app/data/; \
       fi \
    && rm -rf /tmp/data

# ── Runtime ────────────────────────────────────────────────────────────────
FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH \
    HF_HOME=/opt/wren-model-cache \
    HF_HUB_OFFLINE=1 \
    WREN_HOME=/run/wren \
    WREN_PROJECT_HOME=/app/project \
    WREN_MEMORY_BACKEND=lancedb \
    WREN_EMBEDDING_BACKEND=onnx \
    WREN_EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2

RUN apt-get update \
    && apt-get install --no-install-recommends --yes ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 wren \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin wren

WORKDIR /app/project

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/project /app/project
COPY --from=builder /app/data /app/data
COPY --from=builder /opt/wren-model-cache /opt/wren-model-cache

COPY docker/ /app/docker/
COPY scripts/ /app/scripts/

# Semantic sources, compiled MDL, fixture and model cache stay read-only for the
# runtime user; only the derived memory directory is writable.
COPY config/wren-config.json /run/wren/config.json

RUN chmod -R a+rX /app/.venv /app/project /app/data /app/docker /app/scripts /opt/wren-model-cache /run/wren \
    && mkdir -p /app/project/.wren \
    && chown 10001:10001 /app/project/.wren

USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD ["python", "-c", "import socket; socket.create_connection(('127.0.0.1', 8080), 3).close()"]

ENTRYPOINT ["/bin/sh", "/app/docker/entrypoint.sh"]
