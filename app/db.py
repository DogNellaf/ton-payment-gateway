"""Async database layer (asyncpg) with fully parameterized queries."""

from __future__ import annotations

from pathlib import Path

import asyncpg

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class Database:
    """Thin repository around an asyncpg connection pool."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database.connect() must be called first")
        return self._pool

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn)
        await self._apply_schema()

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _apply_schema(self) -> None:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        async with self.pool.acquire() as conn:
            await conn.execute(schema)

    # --- invoices -----------------------------------------------------------

    async def create_invoice(
        self,
        *,
        reference: str,
        chat_id: int,
        amount_nano: int,
        description: str | None,
        ttl_minutes: int,
    ) -> asyncpg.Record:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                INSERT INTO invoices (reference, chat_id, amount_nano, description, expires_at)
                VALUES ($1, $2, $3, $4, now() + make_interval(mins => $5))
                RETURNING *
                """,
                reference,
                chat_id,
                amount_nano,
                description,
                ttl_minutes,
            )

    async def get_pending_by_reference(self, reference: str) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM invoices WHERE reference = $1 AND status = 'pending'",
                reference,
            )

    async def mark_paid(
        self,
        *,
        reference: str,
        payer_address: str,
        tx_hash: str,
        paid_amount_nano: int,
    ) -> asyncpg.Record | None:
        """Atomically flip a pending invoice to paid. Returns ``None`` if it was
        already settled (guards against double-processing a transaction)."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                UPDATE invoices
                   SET status = 'paid',
                       payer_address = $2,
                       tx_hash = $3,
                       paid_amount_nano = $4,
                       paid_at = now()
                 WHERE reference = $1 AND status = 'pending'
                RETURNING *
                """,
                reference,
                payer_address,
                tx_hash,
                paid_amount_nano,
            )

    async def expire_due(self) -> list[asyncpg.Record]:
        """Mark overdue pending invoices as expired and return them."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                UPDATE invoices
                   SET status = 'expired'
                 WHERE status = 'pending' AND expires_at < now()
                RETURNING reference, chat_id
                """
            )

    async def list_by_chat(self, chat_id: int, limit: int = 10) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT * FROM invoices
                 WHERE chat_id = $1
                 ORDER BY created_at DESC
                 LIMIT $2
                """,
                chat_id,
                limit,
            )

    # --- watcher cursor -----------------------------------------------------

    async def get_state(self, key: str) -> str | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT value FROM gateway_state WHERE key = $1", key
            )

    async def set_state(self, key: str, value: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO gateway_state (key, value) VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                key,
                value,
            )
