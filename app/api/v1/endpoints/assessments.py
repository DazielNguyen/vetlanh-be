from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.assessment import PHQ9_QUESTIONS, PHQ9ReminderResponse, PHQ9Result, PHQ9SubmitRequest
from app.services.assessment import get_latest_phq9, get_phq9_history, get_phq9_reminder, submit_phq9
from app.services.goals import suggest_goals

router = APIRouter(prefix="/assessments", tags=["assessments"])


def _to_result(assessment, score_delta: int | None = None) -> PHQ9Result:
    return PHQ9Result(
        id=assessment.id,
        score=assessment.score,
        severity=assessment.severity,
        answers=[getattr(assessment, f"q{i}") for i in range(1, 10)],
        questions=PHQ9_QUESTIONS,
        submitted_at=assessment.created_at,
        suggested_goals=suggest_goals(assessment.severity),
        score_delta=score_delta,
    )


@router.get("/phq9/questions")
async def get_phq9_questions():
    return {"questions": PHQ9_QUESTIONS}


@router.post("/phq9", response_model=PHQ9Result, status_code=201)
async def submit_phq9_assessment(
    payload: PHQ9SubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    previous = await get_latest_phq9(db, current_user.id)
    assessment = await submit_phq9(db, current_user.id, payload.answers)
    delta = assessment.score - previous.score if previous else None
    return _to_result(assessment, score_delta=delta)


@router.get("/phq9/latest", response_model=PHQ9Result)
async def get_latest_phq9_assessment(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assessment = await get_latest_phq9(db, current_user.id)
    if not assessment:
        raise HTTPException(status_code=404, detail="No PHQ-9 assessment found")
    return _to_result(assessment)


@router.get("/phq9/history", response_model=list[PHQ9Result])
async def get_phq9_history_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return PHQ-9 assessments newest-first (paginated), each with score_delta vs previous."""
    pairs = await get_phq9_history(db, current_user.id, limit=limit, offset=offset)
    return [_to_result(assessment, score_delta=delta) for assessment, delta in pairs]


@router.get("/phq9/reminder", response_model=PHQ9ReminderResponse)
async def get_phq9_reminder_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return whether the user is due for a PHQ-9 reassessment (14-day cycle)."""
    return await get_phq9_reminder(db, current_user.id)
