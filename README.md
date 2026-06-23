# TON Payment Gateway Bot

> 🇬🇧 English | [🇷🇺 Русский](README.ru.md)

A Telegram bot that accepts TON payments through invoices. A user requests an invoice for a given amount, gets a one-tap Tonkeeper payment link with a unique comment, and the bot automatically confirms the payment by watching the merchant wallet on-chain.

> Receive-only by design: the gateway never holds private keys or signs transactions. It only needs the merchant's **public** wallet address and a read-only HTTP API key.

## Features

- 🧾 **Invoice creation** — request any amount in TON via an inline menu.
- 🔗 **Tonkeeper deep links** — payment amount and comment are pre-filled.
- 👁️ **On-chain watcher** — a background job polls the wallet and matches incoming transfers to invoices by their unique comment.
- 🔔 **Automatic confirmation** — the buyer is notified the moment a payment lands.
- ⏳ **Invoice lifecycle** — `pending → paid → expired`, with automatic expiry.
- 💰 **Integer money** — amounts are stored as nanotons (`BIGINT`), never floats.

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.11, asyncio |
| Bot framework | python-telegram-bot 21 (with `JobQueue`) |
| Database | PostgreSQL via asyncpg |
| Blockchain API | toncenter v2 HTTP API (aiohttp) |
| Testing | pytest |

## Requirements

- Python 3.11+
- PostgreSQL

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Create a Postgres database
createdb ton_gateway

# Configure environment
cp .env.example .env
# Edit .env: BOT_TOKEN, MERCHANT_WALLET, DATABASE_URL, ...

# Run the bot
python -m app
```

The schema is created automatically on first start.

> **Tip:** try it on testnet first — set `TON_API_BASE_URL=https://testnet.toncenter.com` and `TONKEEPER_TRANSFER_URL=https://test.tonkeeper.com/transfer`.

## Environment Variables

| Variable | Required | Default | Description |
|---|:---:|---|---|
| `BOT_TOKEN` | ✅ | — | Telegram bot token from @BotFather |
| `DATABASE_URL` | ✅ | — | Postgres DSN |
| `MERCHANT_WALLET` | ✅ | — | Public receiving address |
| `TON_API_BASE_URL` | | `https://toncenter.com` | toncenter base URL |
| `TON_API_KEY` | | — | toncenter API key (higher rate limits) |
| `TONKEEPER_TRANSFER_URL` | | `https://app.tonkeeper.com/transfer` | Deep-link base for payment buttons |
| `INVOICE_TTL_MINUTES` | | `30` | How long an invoice stays payable |
| `POLL_INTERVAL_SECONDS` | | `20` | Wallet polling interval |
| `MIN_AMOUNT_TON` | | `0.01` | Minimum invoice amount |
| `MAX_AMOUNT_TON` | | `100` | Maximum invoice amount |

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Unit tests cover money math, payment-link building, and transaction parsing — all without a network or database.

## Project Structure

```
app/
  __init__.py
  __main__.py      # python -m app
  config.py        # settings from environment (.env)
  ton.py           # amount math, payment links, toncenter client
  db.py            # asyncpg repository, parameterized queries
  watcher.py       # background invoice-settlement job
  bot.py           # Telegram handlers + application wiring
  schema.sql       # database schema (nanotons as BIGINT)
tests/
  test_ton.py      # pure-function unit tests
.env.example
requirements.txt
```

## Security Notes

- No private keys: the service is **receive-only**.
- Secrets live in `.env` (git-ignored); nothing sensitive is committed.
- All SQL is parameterized via asyncpg — no string interpolation into queries.
- Money is handled as integer nanotons to avoid floating-point drift.

## License

[MIT](LICENSE)
