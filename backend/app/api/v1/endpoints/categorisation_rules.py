import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.categorisation_rule import CategorisationRule, MatchType
from app.models.user import User
from app.schemas.categorisation_rule import (
    CategorisationRuleCreate,
    CategorisationRuleOut,
    CategorisationRuleUpdate,
    RecategoriseResult,
)
from app.services.auth import get_current_user
from app.services.categorisation import recategorise_uncategorised

router = APIRouter(prefix="/categorisation-rules", tags=["categorisation-rules"])


def _validate_regex_if_needed(match_type: MatchType, value: str) -> None:
    if match_type == MatchType.regex:
        try:
            re.compile(value)
        except re.error as exc:
            raise HTTPException(status_code=422, detail=f"Invalid regex: {exc}")


@router.get("/", response_model=list[CategorisationRuleOut])
def list_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(CategorisationRule)
        .filter(CategorisationRule.user_id == current_user.id)
        .order_by(CategorisationRule.priority.asc(), CategorisationRule.created_at.asc())
        .all()
    )


@router.post("/", response_model=CategorisationRuleOut, status_code=201)
def create_rule(
    data: CategorisationRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validate_regex_if_needed(data.match_type, data.match_value)
    rule = CategorisationRule(**data.model_dump(), user_id=current_user.id)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=CategorisationRuleOut)
def update_rule(
    rule_id: int,
    data: CategorisationRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = (
        db.query(CategorisationRule)
        .filter(CategorisationRule.id == rule_id, CategorisationRule.user_id == current_user.id)
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    payload = data.model_dump(exclude_none=True)
    # Re-validate regex if the match_type/value changed
    final_type = payload.get("match_type", rule.match_type)
    final_value = payload.get("match_value", rule.match_value)
    _validate_regex_if_needed(MatchType(final_type) if not isinstance(final_type, MatchType) else final_type, final_value)
    for k, v in payload.items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = (
        db.query(CategorisationRule)
        .filter(CategorisationRule.id == rule_id, CategorisationRule.user_id == current_user.id)
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()


@router.post("/apply", response_model=RecategoriseResult)
def apply_rules_now(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run rules against every currently uncategorised (Category.other) expense."""
    updated = recategorise_uncategorised(current_user.id, db)
    return {"updated": updated}
