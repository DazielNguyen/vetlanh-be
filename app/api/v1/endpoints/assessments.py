from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.assessment import PHQ9Result, PHQ9SubmitRequest
from app.services.assessment import get_latest_phq9, submit_phq9

router = APIRouter(prefix="/assessments", tags=["assessments"])

PHQ9_QUESTIONS = [
    "Ít hứng thú hoặc không thấy vui khi làm việc",
    "Cảm thấy buồn, chán nản hoặc tuyệt vọng",
    "Khó ngủ, ngủ không yên giấc, hoặc ngủ quá nhiều",
    "Cảm thấy mệt mỏi hoặc ít năng lượng",
    "Ăn không ngon miệng hoặc ăn quá nhiều",
    "Cảm thấy bản thân tệ — hoặc thất bại, đã phụ lòng bản thân/gia đình",
    "Khó tập trung vào công việc, như đọc báo hoặc xem TV",
    "Cử động hoặc nói chuyện chậm chạp đến mức người khác nhận ra; hoặc ngược lại bồn chồn đến mức không ngồi yên được",
    "Có ý nghĩ rằng thà chết còn hơn, hoặc muốn tự làm hại bản thân",
]


@router.get("/phq9/questions")
async def get_phq9_questions():
    """Return the 9 PHQ-9 questions for display in the frontend."""
    return {"questions": PHQ9_QUESTIONS}


@router.post("/phq9", response_model=PHQ9Result, status_code=201)
async def submit_phq9_assessment(
    payload: PHQ9SubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assessment = await submit_phq9(db, current_user.id, payload.answers)
    return PHQ9Result(
        id=assessment.id,
        score=assessment.score,
        severity=assessment.severity,
        answers=[assessment.q1, assessment.q2, assessment.q3, assessment.q4,
                 assessment.q5, assessment.q6, assessment.q7, assessment.q8, assessment.q9],
        questions=PHQ9_QUESTIONS,
        submitted_at=assessment.created_at,
    )


@router.get("/phq9/latest", response_model=PHQ9Result)
async def get_latest_phq9_assessment(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assessment = await get_latest_phq9(db, current_user.id)
    if not assessment:
        raise HTTPException(status_code=404, detail="No PHQ-9 assessment found")
    return PHQ9Result(
        id=assessment.id,
        score=assessment.score,
        severity=assessment.severity,
        answers=[assessment.q1, assessment.q2, assessment.q3, assessment.q4,
                 assessment.q5, assessment.q6, assessment.q7, assessment.q8, assessment.q9],
        questions=PHQ9_QUESTIONS,
        submitted_at=assessment.created_at,
    )
