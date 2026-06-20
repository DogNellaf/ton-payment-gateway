-- Schema for the TON Payment Gateway.
-- Amounts are stored as integer nanotons (1 TON = 1e9 nanotons) to avoid
-- floating-point rounding errors when handling money.

CREATE TABLE IF NOT EXISTS invoices (
    id               BIGSERIAL PRIMARY KEY,
    reference        TEXT        NOT NULL UNIQUE,           -- payment comment, e.g. INV-7F3A9C
    chat_id          BIGINT      NOT NULL,                  -- Telegram chat to notify
    amount_nano      BIGINT      NOT NULL CHECK (amount_nano > 0),
    status           TEXT        NOT NULL DEFAULT 'pending'
                                 CHECK (status IN ('pending', 'paid', 'expired')),
    description      TEXT,
    payer_address    TEXT,                                  -- filled on payment
    tx_hash          TEXT,                                  -- filled on payment
    paid_amount_nano BIGINT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at       TIMESTAMPTZ NOT NULL,
    paid_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices (status);
CREATE INDEX IF NOT EXISTS idx_invoices_chat ON invoices (chat_id);

-- Simple key/value store for the transaction watcher cursor.
CREATE TABLE IF NOT EXISTS gateway_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
