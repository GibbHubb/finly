"""
CSV import service — parses ING and ABN AMRO bank export formats.

ING columns (semicolon-delimited):
  Datum;Naam / Omschrijving;Rekening;Tegenrekening;Code;Af Bij;Bedrag (EUR);MutatieSoort;Mededelingen

ABN AMRO columns (tab-delimited):
  Datum\tOmschrijving\tBedrag  (or comma-delimited variant)

Also exposes a generic mapped-import path used by the column-mapping wizard
(F9) — see `parse_preview` and `commit_mapped_import`.
"""
import csv
import hashlib
import logging
import io
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.import_mapping import ImportMapping
from app.models.transaction import Category, Transaction, TransactionType
from app.models.user import User
from app.services.categorisation import match_description
from app.services.transactions import FX_UNAVAILABLE_IMPORT, _require_base_amount

logger = logging.getLogger(__name__)

# ING format: "Af" = expense, "Bij" = income
_ING_REQUIRED = {"Datum", "Naam / Omschrijving", "Af Bij", "Bedrag (EUR)"}
# ABN AMRO format
_ABN_REQUIRED = {"Datum", "Omschrijving", "Bedrag"}


def _detect_format(headers: list[str]) -> str | None:
    header_set = {h.strip() for h in headers}
    if _ING_REQUIRED.issubset(header_set):
        return "ing"
    if _ABN_REQUIRED.issubset(header_set):
        return "abn"
    return None


def _parse_dutch_decimal(value: str) -> Decimal:
    """Convert Dutch comma-decimal (e.g. '1.234,56' or '1234,56') to Decimal."""
    cleaned = value.strip().replace(".", "").replace(",", ".")
    return Decimal(cleaned)


def _parse_date_ddmmyyyy(value: str) -> date:
    """Parse DD-MM-YYYY or YYYYMMDD."""
    v = value.strip()
    if "-" in v:
        day, month, year = v.split("-")
        return date(int(year), int(month), int(day))
    # YYYYMMDD (ING sometimes uses this)
    return date(int(v[:4]), int(v[4:6]), int(v[6:8]))


def _legacy_hash(tx_date: date, amount: Decimal, description: str) -> str:
    """The pre-F41 hash: date|amount|description with no user. Still READ for dedup, because
    rows imported before F41 carry it; never written any more."""
    raw = f"{tx_date.isoformat()}|{amount}|{description.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _make_hash(user_id: int, tx_date: date, amount: Decimal, description: str) -> str:
    """F41 — the import hash is per USER.

    `transactions.import_hash` has a GLOBAL unique index, while every dedup lookup is scoped to
    one user. With a user-less hash, the second person to import a row anyone else already had
    (a 2.50 Albert Heijn) sailed past their own lookup and died on the index: a 500, and the
    whole file lost. Putting the user into the value makes a cross-user collision impossible
    under the index that already exists, so no schema migration and no backfill are needed.
    """
    raw = f"{user_id}|{tx_date.isoformat()}|{amount}|{description.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def find_existing_import(user_id: int, tx_date: date, amount: Decimal, description: str, db: Session):
    """(new hash, already-imported?) — matches both the per-user hash and the legacy one, so a
    file imported before F41 still dedupes after it."""
    new = _make_hash(user_id, tx_date, amount, description)
    legacy = _legacy_hash(tx_date, amount, description)
    exists = (
        db.query(Transaction.id)
        .filter(Transaction.user_id == user_id, Transaction.import_hash.in_([new, legacy]))
        .first()
    )
    return new, exists is not None


def commit_import(db: Session) -> None:
    """Commit an import batch. A unique-index hit here means a concurrent request (a
    double-clicked upload) inserted the same rows between our dedup check and this commit:
    roll back and say so, instead of a 500 that loses the batch silently."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Only a clash on the import hash means "someone else imported these rows first". Any
        # other constraint is a real fault: let it surface (and be logged) as one, rather than
        # telling the user to retry something that will fail the same way.
        if "import_hash" not in str(exc.orig):
            raise
        raise HTTPException(
            status_code=409,
            detail="Another import of the same rows finished first, so nothing was imported. "
                   "Import the file again to add anything still missing.",
        )


def _infer_category(description: str) -> Category:
    desc = description.lower()
    if any(k in desc for k in ("albert heijn", "jumbo", "lidl", "aldi", "plus", "dirk", "supermarkt", "boodschap")):
        return Category.food
    if any(k in desc for k in ("ns ", "ovchipkaart", "gvb", "ret ", "htm ", "connexxion", "ov-chipkaart", "benzine", "bp ", "shell", "total ")):
        return Category.transport
    if any(k in desc for k in ("huur", "hypotheek", "energie", "nuon", "vattenfall", "essent", "eneco", "ziggo", "kpn", "t-mobile", "vodafone")):
        return Category.housing
    if any(k in desc for k in ("apotheek", "huisarts", "tandarts", "ziekenhuis", "zorgverzekeraar", "vgz", "cz ", "menzis")):
        return Category.health
    if any(k in desc for k in ("h&m", "zara", "primark", "coolblue", "bol.com", "amazon", "mediamarkt")):
        return Category.shopping
    if any(k in desc for k in ("bioscoop", "spotify", "netflix", "disney", "pathe", "theater")):
        return Category.entertainment
    if any(k in desc for k in ("salaris", "loon", "werkgever", "payroll")):
        return Category.salary
    return Category.other


def _parse_ing_row(row: dict) -> tuple[date, Decimal, TransactionType, str] | None:
    """Returns (date, amount, type, description) or None on parse error."""
    try:
        tx_date = _parse_date_ddmmyyyy(row["Datum"])
        amount = _parse_dutch_decimal(row["Bedrag (EUR)"])
        direction = row["Af Bij"].strip()
        tx_type = TransactionType.expense if direction == "Af" else TransactionType.income
        description = row.get("Naam / Omschrijving", "").strip()
        return tx_date, amount, tx_type, description
    except (KeyError, ValueError, InvalidOperation):
        return None


def _parse_abn_row(row: dict) -> tuple[date, Decimal, TransactionType, str] | None:
    try:
        tx_date = _parse_date_ddmmyyyy(row["Datum"])
        raw_amount = row["Bedrag"].strip()
        # ABN AMRO: negative = expense, positive = income
        amount = _parse_dutch_decimal(raw_amount.lstrip("-"))
        tx_type = TransactionType.expense if raw_amount.startswith("-") else TransactionType.income
        description = row.get("Omschrijving", "").strip()
        return tx_date, amount, tx_type, description
    except (KeyError, ValueError, InvalidOperation):
        return None


def _user_base_currency(user_id: int, db: Session) -> str:
    user = db.query(User).filter(User.id == user_id).first()
    return (user.base_currency if user else "EUR") or "EUR"


def _compute_base_amount(amount: Decimal, tx_currency: str, base_currency: str, on_date: date, db: Session) -> Decimal | None:
    """F57 — price one imported row, refusing the WHOLE import (503) if a needed rate is missing.

    Both import paths call this for every row BEFORE adding any row to the session, so a
    refusal leaves nothing behind. That ordering matters twice over: a rate-cache miss commits
    the session (`rates_service._persist_rates`), which would otherwise flush the rows added so
    far into a half-import; and the old behaviour stored NULL for the failed row inside an
    otherwise successful batch — the F56 problem, created fresh on every outage."""
    return _require_base_amount(amount, tx_currency, on_date, base_currency, db, FX_UNAVAILABLE_IMPORT)


def import_csv(
    content: bytes,
    user_id: int,
    db: Session,
) -> dict:
    """
    Parse a bank CSV and insert new transactions.
    Returns { imported, skipped_duplicates, errors }.
    """
    text = content.decode("utf-8-sig", errors="replace")  # handles BOM from Excel exports

    # Try semicolon (ING) first, then comma, then tab
    for delimiter in (";", ",", "\t"):
        sample = text[:2048]
        sniffer_dialect = None
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=delimiter)
            sniffer_dialect = dialect
        except csv.Error:
            pass

        reader = csv.DictReader(io.StringIO(text), dialect=sniffer_dialect or "excel", delimiter=delimiter)
        try:
            headers = reader.fieldnames or []
        except (csv.Error, UnicodeError, ValueError):
            # F51 — narrowed from `except Exception`: an unreadable header for THIS delimiter
            # just means try the next one; anything else is a real fault and should surface.
            headers = []

        fmt = _detect_format(list(headers))
        if fmt:
            break
    else:
        return {"imported": 0, "skipped_duplicates": 0, "errors": ["Unrecognised CSV format — expected ING or ABN AMRO export"]}

    imported = 0
    skipped = 0
    errors: list[str] = []
    base_currency = _user_base_currency(user_id, db)
    pending: list[Transaction] = []  # F57 — added only once every row is priced
    seen_hashes: set[str] = set()

    for i, row in enumerate(reader, start=2):  # start=2: row 1 is header
        parsed = _parse_ing_row(row) if fmt == "ing" else _parse_abn_row(row)
        if parsed is None:
            errors.append(f"Row {i}: could not parse — {dict(row)}")
            continue

        tx_date, amount, tx_type, description = parsed

        # Dedup check (F41: per-user hash, legacy hash still matched)
        import_hash, exists = find_existing_import(user_id, tx_date, amount, description, db)
        # The same row twice in one file: autoflush is off, so the DB check above cannot see the
        # first copy, and both used to reach the unique index on import_hash and 500 the commit.
        if exists or import_hash in seen_hashes:
            skipped += 1
            continue
        seen_hashes.add(import_hash)

        rule_id: int | None = None
        if tx_type == TransactionType.expense:
            match = match_description(description, user_id, db)
            if match is not None:
                category = match.category
                rule_id = match.rule_id
            else:
                category = _infer_category(description)
        else:
            category = Category.salary if "salaris" in description.lower() else Category.other

        tx = Transaction(
            user_id=user_id,
            amount=amount,
            type=tx_type,
            category=category,
            description=description[:500],
            transaction_date=tx_date,
            import_hash=import_hash,
            categorised_by_rule_id=rule_id,
            base_amount=_compute_base_amount(amount, "EUR", base_currency, tx_date, db),
        )
        pending.append(tx)
        imported += 1

    if imported > 0:
        db.add_all(pending)
        commit_import(db)
        # F32: auto-tag recurring transactions after a successful import.
        # Wrapped so a detection failure never breaks the import result.
        try:
            from app.services.recurring_service import apply_recurring_tags
            apply_recurring_tags(user_id, db)
        except Exception:
            # F51 — degrade (the import is already committed), but no longer silently: the old
            # comment said the failure was logged inside apply_recurring_tags, which is not true
            # of an exception that escapes it. Roll back so a failed statement cannot poison
            # the session for whatever runs next in this request.
            logger.exception("import: recurring-tag detection failed for user %s; import kept", user_id)
            db.rollback()

    return {"imported": imported, "skipped_duplicates": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Generic mapped-import path (F9 — column-mapping wizard)
# ---------------------------------------------------------------------------

_DELIMITERS = (",", ";", "\t")

_DATE_FORMATS = {
    "DD-MM-YYYY": "%d-%m-%Y",
    "YYYY-MM-DD": "%Y-%m-%d",
    "DD/MM/YYYY": "%d/%m/%Y",
    "MM/DD/YYYY": "%m/%d/%Y",
    "YYYYMMDD": "%Y%m%d",
}


def _detect_delimiter(sample: str) -> str:
    """Pick the delimiter whose first data line yields the most fields."""
    best = ","
    best_count = 0
    first_line = sample.splitlines()[0] if sample.splitlines() else ""
    for d in _DELIMITERS:
        count = first_line.count(d)
        if count > best_count:
            best_count = count
            best = d
    return best


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="replace")


def parse_preview(content: bytes, delimiter: str | None = None, sample_rows: int = 5) -> dict:
    """
    Extract headers and the first N data rows from an uploaded CSV.
    Auto-detects delimiter when not supplied.
    """
    text = _decode(content)
    delim = delimiter or _detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    headers = [h.strip() for h in (reader.fieldnames or []) if h is not None]

    rows = []
    for i, row in enumerate(reader):
        if i >= sample_rows:
            break
        # Strip any leading/trailing whitespace on keys for display consistency
        rows.append({(k.strip() if k else ""): (v or "") for k, v in row.items()})

    return {"headers": headers, "sample_rows": rows, "delimiter": delim}


def _parse_mapped_date(value: str, fmt_key: str) -> date:
    fmt = _DATE_FORMATS.get(fmt_key)
    if fmt is None:
        raise ValueError(f"Unknown date format: {fmt_key}")
    return datetime.strptime(value.strip(), fmt).date()


def _parse_mapped_decimal(value: str, decimal_format: str) -> Decimal:
    v = value.strip()
    if decimal_format == "comma":
        cleaned = v.replace(".", "").replace(",", ".")
    else:
        cleaned = v.replace(",", "")
    return Decimal(cleaned)


def _match_category(value: str) -> Category:
    if not value:
        return Category.other
    v = value.strip().lower()
    for c in Category:
        if c.value == v:
            return c
    return Category.other


def get_saved_mapping(user_id: int, db: Session) -> dict | None:
    row = db.query(ImportMapping).filter(ImportMapping.user_id == user_id).first()
    if not row:
        return None
    try:
        return json.loads(row.mapping_json)
    except json.JSONDecodeError:
        return None


def _save_mapping(user_id: int, mapping: dict, db: Session) -> None:
    row = db.query(ImportMapping).filter(ImportMapping.user_id == user_id).first()
    payload = json.dumps(mapping)
    if row:
        row.mapping_json = payload
        row.updated_at = datetime.utcnow()
    else:
        db.add(ImportMapping(user_id=user_id, mapping_json=payload))
    db.commit()


def commit_mapped_import(
    content: bytes,
    mapping: dict,
    user_id: int,
    db: Session,
) -> dict:
    """
    Parse a CSV using a user-provided column mapping, dedupe against the
    transactions table, and insert new rows. Persists the mapping.

    mapping keys:
      - date_col (str, required)
      - amount_col (str, required)
      - description_col (str, required)
      - category_col (str, optional — matched against Category enum)
      - delimiter (str, optional — auto-detected if missing)
      - date_format (str, required — one of _DATE_FORMATS keys)
      - decimal_format (str, required — 'comma' or 'dot')
    """
    required = {"date_col", "amount_col", "description_col", "date_format", "decimal_format"}
    missing = required - mapping.keys()
    if missing:
        return {"imported": 0, "skipped_duplicates": 0, "errors": [f"Missing mapping fields: {sorted(missing)}"]}

    text = _decode(content)
    delim = mapping.get("delimiter") or _detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    headers = {h.strip() for h in (reader.fieldnames or []) if h is not None}
    # Validate that referenced columns exist
    for key in ("date_col", "amount_col", "description_col"):
        col = mapping[key]
        if col not in headers:
            return {
                "imported": 0,
                "skipped_duplicates": 0,
                "errors": [f"Column '{col}' not found in file headers"],
            }
    if mapping.get("category_col") and mapping["category_col"] not in headers:
        return {
            "imported": 0,
            "skipped_duplicates": 0,
            "errors": [f"Column '{mapping['category_col']}' not found in file headers"],
        }

    date_col = mapping["date_col"]
    amount_col = mapping["amount_col"]
    desc_col = mapping["description_col"]
    cat_col = mapping.get("category_col")
    date_fmt = mapping["date_format"]
    decimal_fmt = mapping["decimal_format"]

    imported = 0
    skipped = 0
    errors: list[str] = []
    base_currency = _user_base_currency(user_id, db)
    pending: list[Transaction] = []  # F57 — added only once every row is priced
    seen_hashes: set[str] = set()

    for i, raw_row in enumerate(reader, start=2):
        row = {(k.strip() if k else ""): (v or "") for k, v in raw_row.items()}
        try:
            tx_date = _parse_mapped_date(row[date_col], date_fmt)
            raw_amount = row[amount_col].strip()
            negative = raw_amount.startswith("-")
            amount = _parse_mapped_decimal(raw_amount.lstrip("-+"), decimal_fmt)
            if amount <= 0:
                errors.append(f"Row {i}: amount must be non-zero")
                continue
            tx_type = TransactionType.expense if negative else TransactionType.income
            description = row.get(desc_col, "").strip()
        except (KeyError, ValueError, InvalidOperation) as exc:
            errors.append(f"Row {i}: {exc}")
            continue

        rule_id: int | None = None
        if cat_col:
            category = _match_category(row.get(cat_col, ""))
        elif tx_type == TransactionType.expense:
            match = match_description(description, user_id, db)
            if match is not None:
                category = match.category
                rule_id = match.rule_id
            else:
                category = _infer_category(description)
        else:
            category = Category.salary if "salaris" in description.lower() else Category.other

        import_hash, exists = find_existing_import(user_id, tx_date, amount, description, db)
        if exists or import_hash in seen_hashes:  # see import_csv: same row twice in one file
            skipped += 1
            continue
        seen_hashes.add(import_hash)

        tx = Transaction(
            user_id=user_id,
            amount=amount,
            type=tx_type,
            category=category,
            description=description[:500],
            transaction_date=tx_date,
            import_hash=import_hash,
            categorised_by_rule_id=rule_id,
            base_amount=_compute_base_amount(amount, "EUR", base_currency, tx_date, db),
        )
        pending.append(tx)
        imported += 1

    if imported > 0:
        db.add_all(pending)
        commit_import(db)
        # F32: auto-tag recurring transactions after a successful import.
        # Wrapped so a detection failure never breaks the import result.
        try:
            from app.services.recurring_service import apply_recurring_tags
            apply_recurring_tags(user_id, db)
        except Exception:
            # F51 — degrade (the import is already committed), but no longer silently: the old
            # comment said the failure was logged inside apply_recurring_tags, which is not true
            # of an exception that escapes it. Roll back so a failed statement cannot poison
            # the session for whatever runs next in this request.
            logger.exception("import: recurring-tag detection failed for user %s; import kept", user_id)
            db.rollback()

    # Persist the mapping on first successful commit (or update existing)
    if imported > 0 or (skipped > 0 and not errors):
        _save_mapping(user_id, mapping, db)

    return {"imported": imported, "skipped_duplicates": skipped, "errors": errors}
