"""Shared database connection pool for ETL workers."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=settings.dsn,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
        )
    return _pool


@contextmanager
def get_conn() -> Generator[psycopg.Connection, None, None]:
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


def run_migrations() -> None:
    """Apply all SQL migrations on startup."""
    from pathlib import Path

    migrations_dir = Path(__file__).parent.parent / "sql" / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))

    with get_conn() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public.schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        for mf in migration_files:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM public.schema_migrations WHERE filename = %s",
                    (mf.name,),
                )
                if cur.fetchone():
                    continue
            logger.info("Applying migration: %s", mf.name)
            sql = mf.read_text(encoding="utf-8")
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO public.schema_migrations(filename) VALUES (%s)",
                    (mf.name,),
                )
            logger.info("Migration applied: %s", mf.name)
