"""Unified database diagnostics entrypoint for operational checks."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.shared.core.config import get_settings


@dataclass(frozen=True)
class CommandResult:
    name: str
    payload: dict[str, Any]


def _build_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(settings.DATABASE_URL)


async def _run_ping(engine: AsyncEngine) -> CommandResult:
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        row = result.fetchone()
    return CommandResult(name="ping", payload={"ok": bool(row and row[0] == 1)})


async def _run_tables(engine: AsyncEngine) -> CommandResult:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
        )
        tables = [str(row[0]) for row in result.fetchall()]

    return CommandResult(
        name="tables",
        payload={
            "count": len(tables),
            "tables": tables,
            "has_tenant_subscriptions": "tenant_subscriptions" in tables,
            "has_llm_usage": "llm_usage" in tables,
        },
    )


async def _run_partitions(engine: AsyncEngine) -> CommandResult:
    async with engine.connect() as conn:
        count = await conn.scalar(text("SELECT count(*) FROM cost_records"))
        relkind_row = await conn.execute(
            text("SELECT relkind FROM pg_class WHERE relname = 'cost_records'")
        )
        relkind = relkind_row.scalar_one_or_none()
        partition_rows = await conn.execute(
            text(
                "SELECT inhrelid::regclass::text "
                "FROM pg_inherits WHERE inhparent = 'cost_records'::regclass "
                "ORDER BY 1"
            )
        )
        partitions = [str(row[0]) for row in partition_rows.fetchall()]

    return CommandResult(
        name="partitions",
        payload={
            "cost_records_count": int(count or 0),
            "cost_records_relkind": str(relkind) if relkind is not None else None,
            "partitions": partitions,
            "partition_count": len(partitions),
        },
    )


async def _run_inventory(engine: AsyncEngine) -> CommandResult:
    async with engine.connect() as conn:
        res = await conn.execute(
            text(
                """
                SELECT
                    relname as name,
                    pg_size_pretty(pg_total_relation_size(c.oid)) as size,
                    relrowsecurity as rls
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND relkind = 'r'
                  AND relname NOT LIKE 'alembic_%'
                ORDER BY name
                """
            )
        )
        rows = res.fetchall()

    tables = [
        {"name": str(row[0]), "size": str(row[1]), "rls": bool(row[2])}
        for row in rows
    ]
    return CommandResult(
        name="inventory",
        payload={
            "count": len(tables),
            "tables": tables,
        },
    )


async def _run_deep_dive(engine: AsyncEngine) -> CommandResult:
    async with engine.connect() as conn:
        tenant_id = await conn.scalar(text("SELECT id FROM tenants ORDER BY created_at ASC LIMIT 1"))
        if tenant_id is None:
            return CommandResult(
                name="deep-dive",
                payload={"ok": False, "reason": "no_tenant_found"},
            )

        query_specs: tuple[tuple[str, str], ...] = (
            (
                "tenant_sum",
                "SELECT SUM(cost_usd) FROM cost_records WHERE tenant_id = :tenant_id",
            ),
            (
                "tenant_last_90_days",
                "SELECT SUM(cost_usd) FROM cost_records "
                "WHERE tenant_id = :tenant_id AND recorded_at >= :cutoff",
            ),
            (
                "tenant_group_by_service",
                "SELECT service, SUM(cost_usd) FROM cost_records "
                "WHERE tenant_id = :tenant_id GROUP BY service ORDER BY 2 DESC",
            ),
        )

        explain_rows: list[dict[str, Any]] = []
        cutoff = date.today() - timedelta(days=90)
        params = {"tenant_id": str(tenant_id), "cutoff": cutoff}

        for label, sql in query_specs:
            explain_sql = f"EXPLAIN ANALYZE {sql}"
            result = await conn.execute(text(explain_sql), params)
            plan = [str(row[0]) for row in result.fetchall()]
            explain_rows.append({"query": label, "plan": plan})

        total_cost = await conn.scalar(
            text("SELECT COALESCE(SUM(cost_usd), 0) FROM cost_records WHERE tenant_id = :tenant_id"),
            {"tenant_id": str(tenant_id)},
        )

    return CommandResult(
        name="deep-dive",
        payload={
            "ok": True,
            "tenant_id": str(tenant_id),
            "tenant_total_cost_usd": str(total_cost or Decimal("0")),
            "queries": explain_rows,
        },
    )


async def run_command(command: str) -> CommandResult:
    engine = _build_engine()
    try:
        if command == "ping":
            return await _run_ping(engine)
        if command == "tables":
            return await _run_tables(engine)
        if command == "partitions":
            return await _run_partitions(engine)
        if command == "inventory":
            return await _run_inventory(engine)
        if command == "deep-dive":
            return await _run_deep_dive(engine)
        raise ValueError(f"Unsupported command: {command}")
    finally:
        await engine.dispose()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Valdrics DB diagnostics.")
    parser.add_argument(
        "command",
        choices=("ping", "tables", "partitions", "inventory", "deep-dive"),
        help="Diagnostic command to execute.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    result = asyncio.run(run_command(args.command))
    print(result.payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

