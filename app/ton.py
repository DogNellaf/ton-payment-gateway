"""TON helpers: amount conversion, payment links, and a thin toncenter HTTP client.

The gateway only ever *reads* the merchant's incoming transactions, so no private
keys or signing are required here — just a public address and an HTTP API key.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

import aiohttp

NANO = Decimal(10) ** 9


def ton_to_nano(amount: Decimal) -> int:
    """Convert a TON amount to an integer number of nanotons (truncating)."""
    return int((Decimal(amount) * NANO).to_integral_value(rounding=ROUND_DOWN))


def nano_to_ton(nano: int) -> Decimal:
    """Convert nanotons back to a :class:`~decimal.Decimal` TON amount."""
    return Decimal(nano) / NANO


def format_ton(nano: int) -> str:
    """Render nanotons as a human-friendly TON string (no trailing zeros)."""
    value = nano_to_ton(nano).quantize(Decimal("0.000000001")).normalize()
    return f"{value:f}"


def build_payment_link(base_url: str, wallet: str, amount_nano: int, comment: str) -> str:
    """Build a Tonkeeper transfer deep link with a fixed amount and comment."""
    query = urllib.parse.urlencode({"amount": amount_nano, "text": comment})
    return f"{base_url.rstrip('/')}/{wallet}?{query}"


@dataclass(frozen=True)
class IncomingTransfer:
    """A normalized view of an incoming TON transaction."""

    lt: int
    tx_hash: str
    source: str
    amount_nano: int
    comment: str


def parse_incoming(tx: dict) -> IncomingTransfer | None:
    """Extract an :class:`IncomingTransfer` from a toncenter transaction.

    Returns ``None`` for transactions without a real on-chain sender
    (e.g. external messages), which carry no payment we can attribute.
    """
    in_msg = tx.get("in_msg") or {}
    source = in_msg.get("source") or ""
    raw_value = in_msg.get("value")
    if not source or raw_value is None:
        return None
    return IncomingTransfer(
        lt=int(tx["transaction_id"]["lt"]),
        tx_hash=tx["transaction_id"]["hash"],
        source=source,
        amount_nano=int(raw_value),
        comment=(in_msg.get("message") or "").strip(),
    )


class TonClient:
    """Minimal async client over the toncenter v2 HTTP API."""

    def __init__(self, base_url: str, api_key: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def get_transactions(self, address: str, limit: int = 50) -> list[dict]:
        """Fetch the most recent transactions for ``address``."""
        if self._session is None:
            raise RuntimeError("TonClient.start() must be called first")

        params: dict[str, object] = {"address": address, "limit": limit, "archival": "true"}
        if self._api_key:
            params["api_key"] = self._api_key

        url = f"{self._base_url}/api/v2/getTransactions"
        timeout = aiohttp.ClientTimeout(total=20)
        async with self._session.get(url, params=params, timeout=timeout) as resp:
            data = await resp.json()

        if not data.get("ok"):
            raise RuntimeError(f"toncenter error: {data.get('error') or data}")
        return data["result"]
