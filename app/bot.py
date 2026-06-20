"""Telegram bot: invoice creation menu and lifecycle wiring."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .config import Settings, load_settings
from .db import Database
from .ton import TonClient, build_payment_link, format_ton, ton_to_nano
from .watcher import poll_transactions

log = logging.getLogger(__name__)

MAIN, AWAIT_AMOUNT = range(2)

WELCOME = (
    "💎 TON Payment Gateway\n\n"
    "Я помогу принять оплату в TON: создам счёт с уникальным комментарием "
    "и автоматически подтвержу платёж, как только он придёт в сеть.\n\n"
    "Выберите действие:"
)

HELP = (
    "ℹ️ Как это работает\n\n"
    "1. Нажмите «Создать счёт» и укажите сумму в TON.\n"
    "2. Оплатите по ссылке — комментарий к платежу подставляется автоматически.\n"
    "3. Бот следит за кошельком и сам подтвердит оплату по этому комментарию.\n\n"
    "Важно: не меняйте комментарий в платеже — по нему засчитывается оплата."
)

STATUS_EMOJI = {"pending": "⏳", "paid": "✅", "expired": "❌"}


def _main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🧾 Создать счёт", callback_data="create")],
            [InlineKeyboardButton("📋 Мои счета", callback_data="list")],
            [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")],
        ]
    )


def _back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ В меню", callback_data="menu")]]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_chat.send_message(WELCOME, reply_markup=_main_menu())
    return MAIN


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(WELCOME, reply_markup=_main_menu())
    return MAIN


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(HELP, reply_markup=_back_menu())
    return MAIN


async def ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    settings: Settings = context.bot_data["settings"]
    await query.edit_message_text(
        "Введите сумму счёта в TON "
        f"(от {settings.min_amount_ton} до {settings.max_amount_ton}), например 1.5:",
        reply_markup=_back_menu(),
    )
    return AWAIT_AMOUNT


async def create_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    settings: Settings = context.bot_data["settings"]
    db: Database = context.bot_data["db"]

    raw = update.message.text.strip().replace(",", ".")
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        await update.message.reply_text("Не удалось распознать число. Попробуйте ещё раз, например 1.5")
        return AWAIT_AMOUNT

    if amount < settings.min_amount_ton or amount > settings.max_amount_ton:
        await update.message.reply_text(
            f"Сумма должна быть от {settings.min_amount_ton} до {settings.max_amount_ton} TON."
        )
        return AWAIT_AMOUNT

    amount_nano = ton_to_nano(amount)
    reference = f"INV-{uuid4().hex[:8].upper()}"
    await db.create_invoice(
        reference=reference,
        chat_id=update.effective_chat.id,
        amount_nano=amount_nano,
        description=None,
        ttl_minutes=settings.invoice_ttl_minutes,
    )
    link = build_payment_link(
        settings.tonkeeper_transfer_url, settings.merchant_wallet, amount_nano, reference
    )

    await update.message.reply_text(
        "🧾 Счёт создан\n\n"
        f"Сумма: {format_ton(amount_nano)} TON\n"
        f"Комментарий: {reference}\n"
        f"Действителен: {settings.invoice_ttl_minutes} мин\n\n"
        f"⚠️ Укажите комментарий {reference} в платеже — по нему засчитывается оплата.",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("💎 Оплатить в Tonkeeper", url=link)],
                [InlineKeyboardButton("⬅️ В меню", callback_data="menu")],
            ]
        ),
    )
    return MAIN


async def list_invoices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    db: Database = context.bot_data["db"]

    rows = await db.list_by_chat(update.effective_chat.id, limit=10)
    if not rows:
        text = "У вас пока нет счетов."
    else:
        lines = ["📋 Ваши последние счета:\n"]
        for r in rows:
            emoji = STATUS_EMOJI.get(r["status"], "•")
            lines.append(
                f"{emoji} {r['reference']} — {format_ton(r['amount_nano'])} TON — {r['status']}"
            )
        text = "\n".join(lines)

    await query.edit_message_text(text, reply_markup=_back_menu())
    return MAIN


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_chat.send_message(WELCOME, reply_markup=_main_menu())
    return MAIN


def _conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN: [
                CallbackQueryHandler(ask_amount, pattern="^create$"),
                CallbackQueryHandler(list_invoices, pattern="^list$"),
                CallbackQueryHandler(show_help, pattern="^help$"),
                CallbackQueryHandler(show_menu, pattern="^menu$"),
            ],
            AWAIT_AMOUNT: [
                CallbackQueryHandler(show_menu, pattern="^menu$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_invoice),
            ],
        },
        fallbacks=[CommandHandler("start", start), CommandHandler("cancel", cancel)],
    )


async def on_startup(app: Application) -> None:
    settings: Settings = app.bot_data["settings"]

    db = Database(settings.database_url)
    await db.connect()
    ton = TonClient(settings.ton_api_base_url, settings.ton_api_key)
    await ton.start()

    app.bot_data["db"] = db
    app.bot_data["ton"] = ton
    app.job_queue.run_repeating(
        poll_transactions, interval=settings.poll_interval_seconds, first=5
    )
    log.info("Gateway started; watching wallet %s", settings.merchant_wallet)


async def on_shutdown(app: Application) -> None:
    ton: TonClient | None = app.bot_data.get("ton")
    db: Database | None = app.bot_data.get("db")
    if ton is not None:
        await ton.close()
    if db is not None:
        await db.close()


def build_application(settings: Settings) -> Application:
    app = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )
    app.bot_data["settings"] = settings
    app.add_handler(_conversation())
    return app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = load_settings()
    app = build_application(settings)
    app.run_polling(allowed_updates=Update.ALL_TYPES)
