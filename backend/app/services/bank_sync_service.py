"""F27 — Sync one or all GoCardless bank connections.

Mirrors the CSV-import path so budgets/rules behave identically: the same
SHA256(`date|amount|description`) `import_hash` is used for dedup, and the
same `match_description()` engine assigns categories. New rows are
inserted via the same Transaction creation pattern.
"""
from __future__ import annotations

from datetime import date as date_cls, datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.bank_connection import BankConnection
from app.models.transaction import Category, Transaction, TransactionType
from app.services.categorisation import match_description
from app.services.import_service import find_existing_import
from app.services import gocardless_service as gc
from app.services.transactions import _base_amount_for, _needs_rate, _user_base_currency

# F57 — a sync that cannot price a row stores nothing and retries on the next run.
FX_UNAVAILABLE_SYNC = "Exchange rates are unavailable, so nothing was synced. It will retry automatically."




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
    base_currency = _user_base_currency(conn.user_id, db)
    pending: list[Transaction] = []
    seen_hashes: set[str] = set()
    for raw in booked:
        norm = _normalise_tx(raw)
        if not norm:
            continue
        # F41 — the same per-user hash as CSV import (a bank row and a CSV row of the same
        # payment dedupe against each other), legacy hash still matched.
        tx_hash, existing = find_existing_import(
            conn.user_id, norm["transaction_date"], norm["amount"], norm["description"], db,
        )
        if existing or tx_hash in seen_hashes:
            skipped += 1
            continue
        seen_hashes.add(tx_hash)

        # F57 — this path never set base_amount at all, so every synced row was stored NULL and
        # read back as its raw foreign amount (F56). Price it now; if a needed rate is missing,
        # add nothing for this connection and leave it to retry. Nothing has been added to the
        # session yet, so a rate-cache commit inside the conversion cannot flush a partial sync.
        base_amount = _base_amount_for(
            norm["amount"], norm["currency"], norm["transaction_date"], base_currency, db,
        )
        if base_amount is None and _needs_rate(norm["currency"], base_currency):
            # Status deliberately NOT flipped to "error": sync_all_active only picks up
            # active/pending connections, so "error" would end the retries this promises.
            conn.last_error = FX_UNAVAILABLE_SYNC
            return {"inserted": 0, "skipped": skipped, "error": conn.last_error}

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
            base_amount=base_amount,
        )
        pending.append(tx)
        inserted += 1

    db.add_all(pending)
    # Flush so the NEXT connection's dedup query in the same run sees these rows: autoflush is
    # off, and two connections on one account (a reconnect) would otherwise both insert the same
    # hash and fail sync_all_active's single commit for every user.
    db.flush()
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
