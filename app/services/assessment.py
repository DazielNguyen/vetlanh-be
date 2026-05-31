from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment
from app.schemas.assessment import Severity


def calculate_phq9(answers: list[int]) -> tuple[int, str]:
    """Return (score, severity) using DSM-5 PHQ-9 cutoffs."""
    score = sum(answers)
    if score <= 4:
        severity = Severity.MINIMAL
    elif score <= 9:
        severity = Severity.MILD
    elif score <= 14:
        severity = Severity.MODERATE
    else:
        severity = Severity.SEVERE
    return score, severity


async def submit_phq9(db: AsyncSession, user_id: int, answers: list[int]) -> Assessment:
    score, severity = calculate_phq9(answers)
    q1, q2, q3, q4, q5, q6, q7, q8, q9 = answers
    assessment = Assessment(
        user_id=user_id,
        q1=q1, q2=q2, q3=q3, q4=q4, q5=q5,
        q6=q6, q7=q7, q8=q8, q9=q9,
        score=score,
        severity=severity,
    )
    db.add(assessment)
    await db.flush()
    await db.refresh(assessment)
    return assessment


async def get_latest_phq9(db: AsyncSession, user_id: int) -> Assessment | None:
    result = await db.execute(
        select(Assessment)
        .where(Assessment.user_id == user_id)
        .order_by(Assessment.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
