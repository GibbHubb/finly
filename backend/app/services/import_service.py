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
import io
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.models.import_mapping import ImportMapping
from app.models.transaction import Category, Transaction, TransactionType
from app.models.user import User
from app.services.categorisation import match_description
from app.services.rates_service import convert_amount

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


def _make_hash(tx_date: date, amount: Decimal, description: str) -> str:
    raw = f"{tx_date.isoformat()}|{amount}|{description.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


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
    if (tx_currency or "EUR").upper() == base_currency.upper():
        return Decimal(amount).quantize(Decimal("0.01"))
    return convert_amount(Decimal(amount), tx_currency, base_currency, on_date, db)


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
        except Exception:
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

    for i, row in enumerate(reader, start=2):  # start=2: row 1 is header
        parsed = _parse_ing_row(row) if fmt == "ing" else _parse_abn_row(row)
        if parsed is None:
            errors.append(f"Row {i}: could not parse — {dict(row)}")
            continue

        tx_date, amount, tx_type, description = parsed

        import_hash = _make_hash(tx_date, amount, description)

        # Dedup check
        exists = (
            db.query(Transaction.id)
            .filter(Transaction.user_id == user_id, Transaction.import_hash == import_hash)
            .first()
        )
        if exists:
            skipped += 1
            continue

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
        db.add(tx)
        imported += 1

    if imported > 0:
        db.commit()

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

        import_hash = _make_hash(tx_date, amount, description)
        exists = (
            db.query(Transaction.id)
            .filter(Transaction.user_id == user_id, Transaction.import_hash == import_hash)
            .first()
        )
        if exists:
            skipped += 1
            continue

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
        db.add(tx)
        imported += 1

    if imported > 0:
        db.commit()

    # Persist the mapping on first successful commit (or update existing)
    if imported > 0 or (skipped > 0 and not errors):
        _save_mapping(user_id, mapping, db)

    return {"imported": imported, "skipped_duplicates": skipped, "errors": errors}
