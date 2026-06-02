"""Safety plan endpoints — US-024."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.safety_plan import SafetyPlanResponse, SafetyPlanUpsert
from app.services.safety_plan import get_safety_plan, upsert_safety_plan

router = APIRouter(prefix="/safety-plan", tags=["safety-plan"])


@router.get("", response_model=SafetyPlanResponse)
async def read_safety_plan(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """US-024: Return the current user's safety plan."""
    plan = await get_safety_plan(db, current_user.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Safety plan not found")
    return plan


@router.put("", response_model=SafetyPlanResponse)
async def save_safety_plan(
    payload: SafetyPlanUpsert,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """US-024: Create or replace the current user's safety plan."""
    return await upsert_safety_plan(db, current_user.id, payload)
