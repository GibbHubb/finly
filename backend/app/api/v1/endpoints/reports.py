"""F28 — Year-end PDF report endpoint."""
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.services.auth import get_current_user
from app.services.report_service import build_year_review_pdf


router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/year/{year}.pdf")
def year_review_pdf(
    year: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pdf_bytes = build_year_review_pdf(current_user.id, year, db)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="finly-{year}-review.pdf"'},
    )
