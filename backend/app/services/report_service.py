"""F28 — Year-end PDF report ("{year} in review").

Plan deviation: the plan called for WeasyPrint + Jinja2 (HTML/CSS), but
that needs GTK/cairo native libs on Windows (explicitly flagged as a
risk in the plan §8). Substituting reportlab — pure Python, no native
deps, no install pain — same output (totals, top categories with
horizontal bar chart, biggest expense, savings-goal progress).
"""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.budget import Budget  # noqa: F401 — keeps model registered
from app.models.savings_goal import SavingsGoal
from app.models.transaction import Transaction, TransactionType
from app.services.transactions import (
    _excluding_split_parents,
    get_monthly_summary,
)


# Lazy reportlab import so a missing reportlab doesn't crash app startup.
def _rl():
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )
    return {
        "colors": colors, "A4": A4, "cm": cm,
        "styles": getSampleStyleSheet(), "ParagraphStyle": ParagraphStyle,
        "Doc": SimpleDocTemplate, "P": Paragraph, "Sp": Spacer,
        "T": Table, "TS": TableStyle,
    }


def _year_totals(user_id: int, year: int, db: Session) -> dict:
    """Reuse get_monthly_summary across 12 months — year total = sum of the
    twelve monthly summaries (asserted by §3 acceptance)."""
    months = [get_monthly_summary(user_id, m, year, db) for m in range(1, 13)]
    income = sum((Decimal(m["total_income"]) for m in months), Decimal("0"))
    expense = sum((Decimal(m["total_expenses"]) for m in months), Decimal("0"))
    cat_totals: dict[str, Decimal] = {}
    for m in months:
        for c in m["categories"]:
            cat_totals[c["category"]] = cat_totals.get(c["category"], Decimal("0")) + Decimal(c["expenses"])
    return {
        "income": income,
        "expenses": expense,
        "net": income - expense,
        "by_category": sorted(
            [(k, v) for k, v in cat_totals.items() if v > 0],
            key=lambda kv: kv[1],
            reverse=True,
        ),
    }


def _biggest_expense(user_id: int, year: int, db: Session) -> Transaction | None:
    q = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.type == TransactionType.expense,
            func.strftime("%Y", Transaction.transaction_date) == str(year),
        )
        .order_by(Transaction.amount.desc())
    )
    q = _excluding_split_parents(q)
    return q.first()


def _savings_progress(user_id: int, db: Session) -> list[tuple[str, Decimal, Decimal, float]]:
    """All of the user's savings goals: (name, current, target, pct)."""
    goals = db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id).all()
    out = []
    for g in goals:
        cur = Decimal(getattr(g, "current_amount", 0) or 0)
        tgt = Decimal(getattr(g, "target_amount", 0) or 0)
        pct = float(cur / tgt * 100) if tgt > 0 else 0.0
        out.append((g.name, cur, tgt, pct))
    return out


def build_year_review_pdf(user_id: int, year: int, db: Session) -> bytes:
    """Return the PDF bytes for the year-in-review."""
    rl = _rl()
    totals = _year_totals(user_id, year, db)
    biggest = _biggest_expense(user_id, year, db)
    goals = _savings_progress(user_id, db)

    buf = BytesIO()
    doc = rl["Doc"](
        buf, pagesize=rl["A4"],
        leftMargin=2 * rl["cm"], rightMargin=2 * rl["cm"],
        topMargin=2 * rl["cm"], bottomMargin=2 * rl["cm"],
        title=f"finly {year} in review",
    )
    styles = rl["styles"]
    P, Sp, T, TS = rl["P"], rl["Sp"], rl["T"], rl["TS"]
    colors = rl["colors"]

    story = []
    story.append(P(f"finly — {year} in review", styles["Title"]))
    story.append(Sp(1, 0.4 * rl["cm"]))

    # Headline figures.
    has_data = totals["income"] > 0 or totals["expenses"] > 0
    if not has_data:
        story.append(P("No transactions recorded for this year.", styles["Normal"]))
    else:
        story.append(P(
            f"<b>Total income:</b> {totals['income']:.2f}<br/>"
            f"<b>Total expenses:</b> {totals['expenses']:.2f}<br/>"
            f"<b>Net:</b> {totals['net']:.2f}",
            styles["Normal"],
        ))
        story.append(Sp(1, 0.5 * rl["cm"]))

        # Top categories — table + simple horizontal bar (drawn as Table cells).
        story.append(P("Top categories", styles["Heading2"]))
        max_amount = max((amt for _, amt in totals["by_category"]), default=Decimal("1")) or Decimal("1")
        rows = [["Category", "Spent", "Share", ""]]
        total_exp = totals["expenses"] or Decimal("1")
        for cat, amt in totals["by_category"][:8]:  # top 8
            share = float(amt / total_exp * 100)
            # 30-char-wide ASCII bar so we don't need real chart primitives.
            bar_len = int((float(amt) / float(max_amount)) * 30)
            bar = "█" * bar_len
            rows.append([cat, f"{amt:.2f}", f"{share:.1f}%", bar])
        tbl = T(rows, colWidths=[4 * rl["cm"], 3 * rl["cm"], 2.5 * rl["cm"], 6 * rl["cm"]])
        tbl.setStyle(TS([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 1), (2, -1), "RIGHT"),
            ("FONTNAME", (3, 1), (3, -1), "Helvetica"),
            ("TEXTCOLOR", (3, 1), (3, -1), colors.HexColor("#6366f1")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ]))
        story.append(tbl)
        story.append(Sp(1, 0.5 * rl["cm"]))

        if biggest:
            story.append(P("Biggest single expense", styles["Heading2"]))
            story.append(P(
                f"{biggest.transaction_date} — {biggest.description or '(no description)'}<br/>"
                f"<b>{biggest.amount:.2f} {biggest.currency or 'EUR'}</b> · {biggest.category}",
                styles["Normal"],
            ))
            story.append(Sp(1, 0.5 * rl["cm"]))

    if goals:
        story.append(P("Savings goals", styles["Heading2"]))
        rows = [["Goal", "Saved", "Target", "Progress"]]
        for name, cur, tgt, pct in goals:
            rows.append([name, f"{cur:.2f}", f"{tgt:.2f}", f"{pct:.0f}%"])
        tbl = T(rows, colWidths=[5 * rl["cm"], 3 * rl["cm"], 3 * rl["cm"], 3 * rl["cm"]])
        tbl.setStyle(TS([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ]))
        story.append(tbl)

    doc.build(story)
    return buf.getvalue()
