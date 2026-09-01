from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.savings_goal import SavingsGoal
from app.schemas.savings_goal import SavingsGoalCreate, SavingsGoalOut, SavingsGoalUpdate


def _to_out(goal: SavingsGoal) -> SavingsGoalOut:
    target = float(goal.target_amount) or 1.0
    pct = min(100.0, (float(goal.current_amount) / target) * 100.0)
    return SavingsGoalOut(
        id=goal.id,
        name=goal.name,
        target_amount=goal.target_amount,
        current_amount=goal.current_amount,
        deadline=goal.deadline,
        progress_pct=round(pct, 2),
    )


def list_goals(user_id: int, db: Session) -> list[SavingsGoalOut]:
    goals = (
        db.query(SavingsGoal)
        .filter(SavingsGoal.user_id == user_id)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )
    return [_to_out(g) for g in goals]


def create_goal(data: SavingsGoalCreate, user_id: int, db: Session) -> SavingsGoalOut:
    goal = SavingsGoal(
        user_id=user_id,
        name=data.name,
        target_amount=data.target_amount,
        current_amount=Decimal("0"),
        deadline=data.deadline,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _to_out(goal)


def update_goal(goal_id: int, user_id: int, data: SavingsGoalUpdate, db: Session) -> SavingsGoalOut:
    goal = db.query(SavingsGoal).filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == user_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Savings goal not found")

    if data.name is not None:
        goal.name = data.name
    if data.target_amount is not None:
        if data.target_amount <= 0:
            raise HTTPException(status_code=400, detail="Target amount must be greater than zero")
        goal.target_amount = data.target_amount
    if data.current_amount is not None:
        # Clamp at 0 to prevent negative balances
        goal.current_amount = max(Decimal("0"), data.current_amount)
    if data.deadline is not None:
        goal.deadline = data.deadline

    db.commit()
    db.refresh(goal)
    return _to_out(goal)


def delete_goal(goal_id: int, user_id: int, db: Session) -> None:
    goal = db.query(SavingsGoal).filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == user_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Savings goal not found")
    db.delete(goal)
    db.commit()
