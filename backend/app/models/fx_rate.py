from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class FxRate(Base):
    """Cached historical FX rate relative to EUR.

    `rate_vs_eur` follows the ECB / Frankfurter convention: it's the amount of
    `currency` per 1 EUR on `rate_date`. So to convert X USD to EUR on that
    date: X / rate_vs_eur.
    """

    __tablename__ = "fx_rates"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate_vs_eur: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)

    __table_args__ = (
        UniqueConstraint("rate_date", "currency", name="uq_fx_rates_date_currency"),
    )
