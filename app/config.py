"""Application settings, loaded from environment variables (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration for the gateway."""

    bot_token: str
    database_url: str
    merchant_wallet: str
    ton_api_base_url: str
    ton_api_key: str
    tonkeeper_transfer_url: str
    invoice_ttl_minutes: int
    poll_interval_seconds: int
    min_amount_ton: Decimal
    max_amount_ton: Decimal


def load_settings() -> Settings:
    """Build a :class:`Settings` instance from the current environment."""
    return Settings(
        bot_token=_require("BOT_TOKEN"),
        database_url=_require("DATABASE_URL"),
        merchant_wallet=_require("MERCHANT_WALLET"),
        ton_api_base_url=os.getenv("TON_API_BASE_URL", "https://toncenter.com"),
        ton_api_key=os.getenv("TON_API_KEY", ""),
        tonkeeper_transfer_url=os.getenv(
            "TONKEEPER_TRANSFER_URL", "https://app.tonkeeper.com/transfer"
        ),
        invoice_ttl_minutes=int(os.getenv("INVOICE_TTL_MINUTES", "30")),
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "20")),
        min_amount_ton=Decimal(os.getenv("MIN_AMOUNT_TON", "0.01")),
        max_amount_ton=Decimal(os.getenv("MAX_AMOUNT_TON", "100")),
    )
