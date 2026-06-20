"""Pure-function tests for the TON helpers (no network or database needed)."""

from decimal import Decimal

from app.ton import (
    build_payment_link,
    format_ton,
    nano_to_ton,
    parse_incoming,
    ton_to_nano,
)


def test_ton_to_nano():
    assert ton_to_nano(Decimal("1")) == 1_000_000_000
    assert ton_to_nano(Decimal("0.15")) == 150_000_000
    assert ton_to_nano(Decimal("1.5")) == 1_500_000_000


def test_ton_to_nano_truncates_sub_nano():
    # More precision than a nanoton is truncated, never rounded up.
    assert ton_to_nano(Decimal("0.0000000019")) == 1


def test_round_trip():
    assert nano_to_ton(1_500_000_000) == Decimal("1.5")


def test_format_ton_strips_trailing_zeros():
    assert format_ton(1_000_000_000) == "1"
    assert format_ton(1_500_000_000) == "1.5"
    assert format_ton(150_000_000) == "0.15"


def test_build_payment_link():
    link = build_payment_link(
        "https://app.tonkeeper.com/transfer", "UQABC", 150_000_000, "INV-7F3A"
    )
    assert link.startswith("https://app.tonkeeper.com/transfer/UQABC?")
    assert "amount=150000000" in link
    assert "text=INV-7F3A" in link


def test_parse_incoming():
    tx = {
        "transaction_id": {"lt": "123", "hash": "abc"},
        "in_msg": {"source": "UQSENDER", "value": "150000000", "message": "INV-7F3A"},
    }
    transfer = parse_incoming(tx)
    assert transfer is not None
    assert transfer.lt == 123
    assert transfer.amount_nano == 150_000_000
    assert transfer.comment == "INV-7F3A"
    assert transfer.source == "UQSENDER"


def test_parse_incoming_skips_external_message():
    tx = {
        "transaction_id": {"lt": "1", "hash": "h"},
        "in_msg": {"source": "", "value": "1"},
    }
    assert parse_incoming(tx) is None
