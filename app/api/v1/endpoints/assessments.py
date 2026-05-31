from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.assessment import PHQ9_QUESTIONS, PHQ9Result, PHQ9SubmitRequest
from app.services.assessment import get_latest_phq9, submit_phq9
from app.services.goals import suggest_goals

router = APIRouter(prefix="/assessments", tags=["assessments"])


def _to_result(assessment) -> PHQ9Result:
    return PHQ9Result(
        id=assessment.id,
        score=assessment.score,
        severity=assessment.severity,
        answers=[getattr(assessment, f"q{i}") for i in range(1, 10)],
        questions=PHQ9_QUESTIONS,
        submitted_at=assessment.created_at,
        suggested_goals=suggest_goals(assessment.severity),
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
    assessment = await submit_phq9(db, current_user.id, payload.answers)
    return _to_result(assessment)


@router.get("/phq9/latest", response_model=PHQ9Result)
async def get_latest_phq9_assessment(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assessment = await get_latest_phq9(db, current_user.id)
    if not assessment:
        raise HTTPException(status_code=404, detail="No PHQ-9 assessment found")
    return _to_result(assessment)
