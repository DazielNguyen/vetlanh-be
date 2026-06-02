"""Journal prompt endpoints — US-029."""

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.journal_prompt import DailyPromptResponse, JournalPromptOut
from app.services.journal_prompts import _TOPICS, get_daily_prompt, get_next_prompt, list_by_topic

router = APIRouter(prefix="/journal/prompts", tags=["journal"])


@router.get("/daily", response_model=DailyPromptResponse)
async def get_today_prompt(
    current_user: User = Depends(get_current_user),
):
    """US-029: Return today's deterministic reflective prompt for the user."""
    prompt = get_daily_prompt(current_user.id)
    return DailyPromptResponse(
        prompt=JournalPromptOut(**prompt),
        topics=_TOPICS,
    )


@router.get("/next", response_model=JournalPromptOut)
async def next_prompt(
    current_id: int = Query(..., description="ID of the prompt currently shown"),
    _current_user: User = Depends(get_current_user),
):
    """US-029: Return the next prompt after the currently shown one."""
    return JournalPromptOut(**get_next_prompt(current_id))


@router.get("", response_model=list[JournalPromptOut])
async def list_prompts(
    topic: str | None = Query(default=None, description="Filter by topic slug"),
    _current_user: User = Depends(get_current_user),
):
    """US-029: List all prompts, optionally filtered by topic."""
    return [JournalPromptOut(**p) for p in list_by_topic(topic)]
