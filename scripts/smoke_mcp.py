"""End-to-end MCP smoke test for the Jaffle/DuckDB DEV deployment.

Exercises the deployed streamable-HTTP endpoint with the locked MCP SDK and
asserts the observable behaviour a Jaffle deployment must have: the expected
tool surface, the four fixture aggregates, compiled semantics, curated query
memory, and the read-only SQL policy.

Response parsing note: Wren's MCP tools are annotated as bare ``dict``, so the
locked SDK does not populate ``structuredContent``. Every dictionary response
therefore arrives as JSON in a single ``TextContent`` block.

The assertions are specific to the Jaffle fixture by design; point ``--url`` at
a remote deployment only when you expect the same fixture semantics.
"""

from __future__ import annotations

import argparse
import json
import sys

import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError

DEFAULT_URL = "http://127.0.0.1:8080/mcp"

REQUIRED_TOOLS = (
    "run_sql",
    "list_models",
    "get_mdl",
    "get_instructions",
    "get_context",
    "recall_queries",
    "list_stored_queries",
)

CURATED_NL = "How many orders are there?"
CURATED_SQL = "SELECT COUNT(*) AS order_count FROM orders"

ORDER_COUNT_SQL = "SELECT COUNT(*) AS order_count FROM orders"
REVENUE_SQL = "SELECT ROUND(SUM(amount), 2) AS total_revenue_aud FROM orders"
JOINED_SQL = (
    "SELECT COUNT(*) AS joined_orders FROM orders o "
    "JOIN customers c ON o.customer_id = c.customer_id"
)
RAW_TABLE_SQL = "SELECT COUNT(*) AS raw_count FROM jaffle_shop.main.raw_orders"


class SmokeFailure(AssertionError):
    """A smoke assertion failed."""


def require(condition: object, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def payload(result) -> object:
    """Decode a tool result, raising on MCP-level errors."""
    if result.isError:
        text = " ".join(
            block.text for block in result.content if getattr(block, "text", None)
        )
        raise SmokeFailure(f"tool reported isError: {text}")
    texts = [block.text for block in result.content if getattr(block, "text", None)]
    require(texts, "tool returned no text content")
    return json.loads(texts[0])


def tool_names(tools) -> set[str]:
    return {tool.name for tool in tools}


async def call(session: ClientSession, name: str, **arguments) -> object:
    return payload(await session.call_tool(name, arguments))


async def expect_sql_error(session: ClientSession, sql: str, label: str) -> None:
    result = await session.call_tool("run_sql", {"sql": sql})
    require(result.isError, f"{label} must be rejected, got a successful result")


async def expect_tool_rejected(session: ClientSession, name: str, arguments) -> None:
    """Require the server to reject a tool call.

    An unregistered tool is rejected either as an MCP error (JSON-RPC) or as a
    result flagged ``isError``, depending on whether the name is unknown to the
    registry or known-but-refused. Both are failures for the caller, so accept
    either protocol form and reject any successful result.
    """
    try:
        result = await session.call_tool(name, arguments)
    except McpError:
        return
    require(
        result.isError,
        f"{name} must be rejected, got a successful result: {result}",
    )


async def run(url: str) -> None:
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            listing = await session.list_tools()
            names = tool_names(listing.tools)
            missing = [name for name in REQUIRED_TOOLS if name not in names]
            require(not missing, f"missing required tools: {missing}")

            models = await call(session, "list_models")
            model_names = {
                model["name"] for model in models.get("models", models.get("data", []))
            }
            require(
                {"customers", "orders"} <= model_names,
                f"list_models lacks customers/orders: {sorted(model_names)}",
            )

            mdl = await call(session, "get_mdl")
            relationship_names = {rel["name"] for rel in mdl.get("relationships", [])}
            require(
                "orders_customers" in relationship_names,
                f"compiled relationship missing: {sorted(relationship_names)}",
            )

            customers = await call(
                session,
                "run_sql",
                sql="SELECT COUNT(*) AS customer_count FROM customers",
            )
            require(
                customers["rows"] == [{"customer_count": 100}],
                f"unexpected customer count: {customers['rows']}",
            )

            orders = await call(session, "run_sql", sql=ORDER_COUNT_SQL)
            require(
                orders["rows"] == [{"order_count": 99}],
                f"unexpected order count: {orders['rows']}",
            )

            revenue = await call(session, "run_sql", sql=REVENUE_SQL)
            total = revenue["rows"][0]["total_revenue_aud"]
            require(
                abs(float(total) - 1672.00) < 0.005,
                f"unexpected total revenue: {total}",
            )

            joined = await call(session, "run_sql", sql=JOINED_SQL)
            require(
                joined["rows"] == [{"joined_orders": 99}],
                f"unexpected joined order count: {joined['rows']}",
            )

            instructions = json.dumps(await call(session, "get_instructions"))
            for phrase in ("AUD", "revenue", "raw_"):
                require(
                    phrase in instructions,
                    f"get_instructions omits {phrase!r} business rules",
                )

            context = await call(session, "get_context", question="customer orders")
            require(
                context.get("strategy") == "full"
                and "customers" in context.get("schema", "")
                and "orders" in context.get("schema", ""),
                f"unexpected schema context: {context}",
            )

            recalled = await call(session, "recall_queries", question=CURATED_NL)
            require(
                any(row.get("nl_query") == CURATED_NL
                    and row.get("sql_query", "").strip() == CURATED_SQL
                    for row in recalled.get("matches", [])),
                f"recall_queries lost the curated pair: {recalled}",
            )

            stored = await call(session, "list_stored_queries")
            rows = stored.get("queries", [])
            require(
                any(row.get("nl_query") == CURATED_NL
                    and row.get("sql_query", "").strip() == CURATED_SQL for row in rows)
                and all("source:seed" not in (row.get("tags") or "") for row in rows),
                f"unexpected stored queries: {stored}",
            )

            require(
                "store_query" not in names,
                "store_query must be absent without --allow-write",
            )
            await expect_tool_rejected(
                session,
                "store_query",
                {"nl_query": "write probe", "sql_query": "SELECT 1"},
            )
            require(
                await call(session, "list_stored_queries") == stored,
                "stored queries changed after rejected store_query call",
            )
            await expect_sql_error(
                session,
                "DELETE FROM orders",
                "DELETE statement",
            )
            await expect_sql_error(
                session,
                RAW_TABLE_SQL,
                "strict-mode read of a non-MDL raw table",
            )

            remaining = await call(session, "run_sql", sql=ORDER_COUNT_SQL)
            require(
                remaining["rows"] == [{"order_count": 99}],
                f"fixture mutated after rejected writes: {remaining['rows']}",
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=DEFAULT_URL, help="MCP endpoint URL")
    args = parser.parse_args(argv)
    try:
        anyio.run(run, args.url)
    except SmokeFailure as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"MCP smoke passed: Jaffle/DuckDB semantics, curated memory and "
          f"read-only SQL policy verified at {args.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
