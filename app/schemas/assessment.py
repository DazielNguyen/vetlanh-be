from datetime import datetime

from pydantic import BaseModel, Field, field_validator

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


class PHQ9SubmitRequest(BaseModel):
    answers: list[int] = Field(..., min_length=9, max_length=9)

    @field_validator("answers")
    @classmethod
    def validate_answers(cls, v: list[int]) -> list[int]:
        for i, answer in enumerate(v):
            if answer not in (0, 1, 2, 3):
                raise ValueError(f"Answer {i + 1} must be 0, 1, 2, or 3")
        return v


class PHQ9Result(BaseModel):
    id: int
    score: int
    severity: str
    answers: list[int]
    questions: list[str]
    submitted_at: datetime

    model_config = {"from_attributes": True}
