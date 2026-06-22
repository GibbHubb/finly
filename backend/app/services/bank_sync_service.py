"""F27 — Sync one or all GoCardless bank connections.

Mirrors the CSV-import path so budgets/rules behave identically: the same
SHA256(`date|amount|description`) `import_hash` is used for dedup, and the
same `match_description()` engine assigns categories. New rows are
inserted via the same Transaction creation pattern.
"""
from __future__ import annotations

import hashlib
from datetime import date as date_cls, datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.bank_connection import BankConnection
from app.models.transaction import Category, Transaction, TransactionType
from app.services.categorisation import match_description
from app.services import gocardless_service as gc


def _make_hash(tx_date: date_cls, amount: Decimal, description: str) -> str:
    raw = f"{tx_date.isoformat()}|{amount}|{description.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _normalise_tx(raw: dict) -> dict | None:
    """GoCardless booked-transaction → finly tx dict (or None to skip)."""
    amt_obj = raw.get("transactionAmount") or {}
    raw_amount = amt_obj.get("amount")
    currency = (amt_obj.get("currency") or "EUR").upper()
    if raw_amount is None:
        return None
    try:
        amount = Decimal(str(raw_amount))
    except Exception:
        return None
    # GoCardless gives signed amounts: negative = debit (expense).
    tx_type = TransactionType.expense if amount < 0 else TransactionType.income
    amount = abs(amount)

    date_str = (
        raw.get("bookingDate")
        or raw.get("valueDate")
        or raw.get("bookingDateTime")
    )
    if not date_str:
        return None
    try:
        tx_date = date_cls.fromisoformat(date_str[:10])
    except ValueError:
        return None

    description = (
        raw.get("remittanceInformationUnstructured")
        or " ".join(raw.get("remittanceInformationUnstructuredArray") or [])
        or raw.get("creditorName")
        or raw.get("debtorName")
        or ""
    ).strip()

    return {
        "amount": amount,
        "type": tx_type,
        "description": description,
        "transaction_date": tx_date,
        "currency": currency,
    }


def sync_connection(conn: BankConnection, db: Session) -> dict:
    """Pull transactions for `conn`, insert only new (by import_hash).
    Returns counts; flips conn.status on auth/expiry. Caller commits."""
    if not conn.account_id:
        # Resolve the first account from the requisition if we don't have it yet.
        req = gc.get_requisition(conn.requisition_id)
        accounts = req.get("accounts") or []
        if not accounts:
            # F31 — no accounts means consent lapsed; distinct from transient error.
            conn.status = "expired"
            conn.last_error = "Requisition has no accounts — consent has likely lapsed. Please reconnect."
            return {"inserted": 0, "skipped": 0, "error": conn.last_error}
        conn.account_id = accounts[0]

    try:
        data = gc.fetch_transactions(conn.account_id)
    except gc.GoCardlessError as exc:
        if exc.status in (401, 403):
            # F31 — auth/consent failure: use distinct "expired" status so the
            # frontend can render a Reconnect CTA instead of a generic error.
            conn.status = "expired"
            conn.last_error = f"Auth failed ({exc.status}) — consent has expired. Please reconnect."
        else:
            # Transient / unexpected error — keep "error" so it retries next sync.
            conn.status = "error"
            conn.last_error = str(exc)
        return {"inserted": 0, "skipped": 0, "error": conn.last_error}

    booked: Iterable[dict] = (data.get("transactions") or {}).get("booked") or []

    inserted = 0
    skipped = 0
    for raw in booked:
        norm = _normalise_tx(raw)
        if not norm:
            continue
        tx_hash = _make_hash(norm["transaction_date"], norm["amount"], norm["description"])
        existing = (
            db.query(Transaction)
            .filter(Transaction.user_id == conn.user_id, Transaction.import_hash == tx_hash)
            .first()
        )
        if existing:
            skipped += 1
            continue

        # Rules first, then heuristic fallback (other).
        rule_match = match_description(norm["description"], conn.user_id, db)
        category = rule_match.category if rule_match else Category.other
        rule_id = rule_match.rule_id if rule_match else None

        tx = Transaction(
            user_id=conn.user_id,
            amount=norm["amount"],
            type=norm["type"],
            category=category,
            description=norm["description"],
            transaction_date=norm["transaction_date"],
            currency=norm["currency"],
            import_hash=tx_hash,
            categorised_by_rule_id=rule_id,
        )
        db.add(tx)
        inserted += 1

    conn.status = "active"
    conn.last_error = None
    conn.last_sync_at = datetime.utcnow()
    return {"inserted": inserted, "skipped": skipped, "error": None}


def sync_all_active(db: Session) -> dict:
    """Scheduler entry point — sync every active or pending connection."""
    conns = (
        db.query(BankConnection)
        .filter(BankConnection.status.in_(["active", "pending"]))
        .all()
    )
    total_inserted = 0
    total_skipped = 0
    errors = 0
    for c in conns:
        r = sync_connection(c, db)
        total_inserted += r["inserted"]
        total_skipped += r["skipped"]
        if r["error"]:
            errors += 1
    db.commit()
    return {"connections": len(conns), "inserted": total_inserted, "skipped": total_skipped, "errors": errors}
