# Start the host DEV MCP server in the foreground.
dev:
    uv sync --locked
    uv run --frozen python scripts/dev.py
