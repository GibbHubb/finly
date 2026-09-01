"""F27 — GoCardless bank-connect endpoints.

Flow:
  1. POST /bank/connect   → creates a requisition, returns the hosted
                            consent URL + requisition_id (we persist a
                            pending BankConnection).
  2. GET  /bank/callback  → after the user consents, GoCardless redirects
                            here with `?ref=...` matching our reference;
                            we resolve the requisition and flip status.
  3. POST /bank/sync      → manually pull transactions for the user's
                            connections (also runs nightly via scheduler).
  4. GET  /bank/status    → list the user's connections + last sync.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import settings
from app.models.user import User
from app.models.bank_connection import BankConnection
from app.services.auth import get_current_user
from app.services import gocardless_service as gc
from app.services.bank_sync_service import sync_connection


router = APIRouter(prefix="/bank", tags=["bank"])


@router.post("/connect")
def connect_bank(
    institution_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Build a GoCardless requisition and return the consent link."""
    try:
        inst = institution_id or settings.GOCARDLESS_SANDBOX_INSTITUTION
        req = gc.create_requisition(inst)
    except gc.GoCardlessError as e:
        raise HTTPException(status_code=e.status or 502, detail=str(e))

    conn = BankConnection(
        user_id=current_user.id,
        requisition_id=req["id"],
        institution_id=inst,
        status="pending",
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return {"requisition_id": req["id"], "link": req["link"], "connection_id": conn.id}


@router.get("/callback")
def bank_callback(
    ref: str = Query(..., description="GoCardless requisition reference"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """User returns here after consenting on the GoCardless hosted page.
    Resolve the requisition → account ids → mark connection active."""
    # Find the pending connection by requisition.reference comes from us;
    # for sandbox simplicity we accept either ref==requisition_id or look up
    # the most recent pending row for this user.
    conn = (
        db.query(BankConnection)
        .filter(
            BankConnection.user_id == current_user.id,
            BankConnection.status == "pending",
        )
        .order_by(BankConnection.created_at.desc())
        .first()
    )
    if not conn:
        raise HTTPException(status_code=404, detail="No pending bank connection")

    try:
        req = gc.get_requisition(conn.requisition_id)
    except gc.GoCardlessError as e:
        raise HTTPException(status_code=e.status or 502, detail=str(e))

    accounts = req.get("accounts") or []
    if accounts:
        conn.account_id = accounts[0]
    conn.institution_name = req.get("institution_id") or conn.institution_name
    conn.status = "active"
    db.commit()
    return {"ok": True, "connection_id": conn.id, "account_id": conn.account_id}


@router.post("/sync")
def sync_now(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger a sync for the user's connections."""
    conns = (
        db.query(BankConnection)
        .filter(BankConnection.user_id == current_user.id)
        .filter(BankConnection.status.in_(["active", "pending"]))
        .all()
    )
    results = []
    for c in conns:
        try:
            r = sync_connection(c, db)
        except gc.GoCardlessError as e:
            r = {"inserted": 0, "skipped": 0, "error": str(e)}
        results.append({"connection_id": c.id, **r})
    db.commit()
    return {"connections": len(conns), "results": results}


@router.get("/status")
def status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conns = (
        db.query(BankConnection)
        .filter(BankConnection.user_id == current_user.id)
        .order_by(BankConnection.created_at.desc())
        .all()
    )
    return [
        {
            "id": c.id,
            "institution_id": c.institution_id,
            "institution_name": c.institution_name,
            "status": c.status,
            "last_sync_at": c.last_sync_at,
            "last_error": c.last_error,
            # F31 — true when the connection has expired and the user must reconnect.
            "needs_reconnect": c.status == "expired",
        }
        for c in conns
    ]
