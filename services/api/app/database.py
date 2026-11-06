from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, PoolTimeout

from app.config import Settings
from app.errors import DatabaseNotConfigured, DatabaseUnavailable


def _safe_error(exc: Exception) -> str:
    first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    return first_line[:240]


class Database:
    """Small wrapper around a lazily connected psycopg pool."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._url = settings.resolved_database_url
        self._pool: AsyncConnectionPool | None = None

    @property
    def configured(self) -> bool:
        return self._url is not None

    async def open(self) -> None:
        if not self._url:
            return

        self._pool = AsyncConnectionPool(
            conninfo=self._url,
            min_size=self._settings.database_pool_min_size,
            max_size=self._settings.database_pool_max_size,
            open=False,
            timeout=5,
            kwargs={
                "autocommit": True,
                "row_factory": dict_row,
            },
        )
        # Do not block application startup if the database is temporarily down.
        await self._pool.open(wait=False)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def status(self) -> tuple[str, str | None]:
        if not self.configured:
            return "not_configured", None
        if self._pool is None:
            return "unavailable", "Connection pool has not been initialised."

        try:
            async with self._pool.connection(timeout=3) as conn:
                await conn.execute("SELECT 1")
        except Exception as exc:  # pragma: no cover - depends on live database
            return "unavailable", _safe_error(exc)
        return "connected", None

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[psycopg.AsyncConnection]:
        if not self.configured or self._pool is None:
            raise DatabaseNotConfigured()

        try:
            async with self._pool.connection(timeout=5) as conn:
                timeout = self._settings.statement_timeout_ms
                await conn.execute(
                    sql.SQL("SET statement_timeout = {}").format(sql.Literal(timeout))
                )
                yield conn
        except PoolTimeout as exc:
            raise DatabaseUnavailable("Database connection timed out.") from exc
        except psycopg.OperationalError as exc:
            raise DatabaseUnavailable(_safe_error(exc)) from exc
