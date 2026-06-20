"""Background watcher: polls the merchant wallet and settles matching invoices.

Runs as a repeating ``JobQueue`` job inside the bot's event loop, so it shares
the same database pool and HTTP session and can notify users directly.
"""

from __future__ import annotations

import logging

from telegram.ext import ContextTypes

from .db import Database
from .ton import TonClient, format_ton, parse_incoming

log = logging.getLogger(__name__)

STATE_LAST_LT = "watcher_last_lt"


async def _notify(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> None:
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except Exception as exc:  # noqa: BLE001 — notification must never crash the poll
        log.warning("Failed to notify chat %s: %s", chat_id, exc)


async def poll_transactions(context: ContextTypes.DEFAULT_TYPE) -> None:
    """One polling cycle: expire stale invoices, then match new payments."""
    app = context.application
    db: Database = app.bot_data["db"]
    ton: TonClient = app.bot_data["ton"]
    settings = app.bot_data["settings"]

    # 1. Cancel invoices that ran out of time.
    for row in await db.expire_due():
        await _notify(
            context,
            row["chat_id"],
            f"⏳ Счёт {row['reference']} истёк и был отменён.",
        )

    # 2. Pull recent transactions for the merchant wallet.
    try:
        transactions = await ton.get_transactions(settings.merchant_wallet, limit=50)
    except Exception as exc:  # noqa: BLE001 — network/API hiccups are expected
        log.warning("Failed to fetch transactions: %s", exc)
        return

    last_lt = int(await db.get_state(STATE_LAST_LT) or 0)
    max_lt = last_lt

    # Process oldest-first so the cursor advances monotonically.
    for tx in sorted(transactions, key=lambda t: int(t["transaction_id"]["lt"])):
        transfer = parse_incoming(tx)
        if transfer is None or transfer.lt <= last_lt:
            continue
        max_lt = max(max_lt, transfer.lt)

        if not transfer.comment:
            continue
        invoice = await db.get_pending_by_reference(transfer.comment)
        if invoice is None or transfer.amount_nano < invoice["amount_nano"]:
            continue

        paid = await db.mark_paid(
            reference=transfer.comment,
            payer_address=transfer.source,
            tx_hash=transfer.tx_hash,
            paid_amount_nano=transfer.amount_nano,
        )
        if paid is not None:
            log.info("Invoice %s settled by %s", paid["reference"], transfer.source)
            await _notify(
                context,
                paid["chat_id"],
                "✅ Оплата получена!\n"
                f"Счёт: {paid['reference']}\n"
                f"Сумма: {format_ton(transfer.amount_nano)} TON\n"
                "Статус: PAID",
            )

    if max_lt > last_lt:
        await db.set_state(STATE_LAST_LT, str(max_lt))
