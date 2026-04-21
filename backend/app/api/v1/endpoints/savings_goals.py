from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.savings_goal import SavingsGoalCreate, SavingsGoalOut, SavingsGoalUpdate
from app.services.auth import get_current_user
from app.services.savings_goals import create_goal, delete_goal, list_goals, update_goal

router = APIRouter(prefix="/savings-goals", tags=["savings-goals"])


@router.get("/", response_model=list[SavingsGoalOut])
def list_savings_goals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all savings goals for the authenticated user."""
    return list_goals(current_user.id, db)


@router.post("/", response_model=SavingsGoalOut, status_code=201)
def add_savings_goal(
    data: SavingsGoalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new savings goal."""
    return create_goal(data, current_user.id, db)


@router.patch("/{goal_id}", response_model=SavingsGoalOut)
def edit_savings_goal(
    goal_id: int,
    data: SavingsGoalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a savings goal (name, target, current amount, deadline)."""
    return update_goal(goal_id, current_user.id, data, db)


@router.delete("/{goal_id}", status_code=204)
def remove_savings_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a savings goal."""
    delete_goal(goal_id, current_user.id, db)
