"""
CSV import service — parses ING and ABN AMRO bank export formats.

ING columns (semicolon-delimited):
  Datum;Naam / Omschrijving;Rekening;Tegenrekening;Code;Af Bij;Bedrag (EUR);MutatieSoort;Mededelingen

ABN AMRO columns (tab-delimited):
  Datum\tOmschrijving\tBedrag  (or comma-delimited variant)
"""
import csv
import hashlib
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.models.transaction import Category, Transaction, TransactionType

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

        category = _infer_category(description) if tx_type == TransactionType.expense else (
            Category.salary if "salaris" in description.lower() else Category.other
        )

        tx = Transaction(
            user_id=user_id,
            amount=amount,
            type=tx_type,
            category=category,
            description=description[:500],
            transaction_date=tx_date,
            import_hash=import_hash,
        )
        db.add(tx)
        imported += 1

    if imported > 0:
        db.commit()

    return {"imported": imported, "skipped_duplicates": skipped, "errors": errors}
