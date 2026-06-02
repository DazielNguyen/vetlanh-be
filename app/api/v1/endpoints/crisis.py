"""Crisis support endpoints — US-023.

Provides static crisis resources: hotline numbers and a breathing exercise
link. No authentication required — a user in crisis must never be blocked
by a login gate.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/crisis", tags=["crisis"])


class HotlineInfo(BaseModel):
    name: str
    number: str
    description: str
    available: str


class BreathingRef(BaseModel):
    exercise_slug: str
    title: str
    description: str


class CrisisResourcesResponse(BaseModel):
    hotlines: list[HotlineInfo]
    breathing_exercise: BreathingRef
    message: str


_RESOURCES = CrisisResourcesResponse(
    message="Bạn không đơn độc. Chúng tôi ở đây cùng bạn.",
    hotlines=[
        HotlineInfo(
            name="Đường dây hỗ trợ sức khỏe tâm thần — Bộ Y tế",
            number="1800 599 920",
            description="Miễn phí, 24/7, bảo mật",
            available="24/7",
        ),
        HotlineInfo(
            name="Đường dây hỗ trợ khẩn cấp",
            number="113",
            description="Cảnh sát — khi có nguy hiểm ngay lập tức",
            available="24/7",
        ),
    ],
    breathing_exercise=BreathingRef(
        exercise_slug="breathing-4-7-8",
        title="Thở 4-7-8",
        description="Bài thở giúp bình tĩnh ngay lập tức. Hít vào 4 giây, giữ 7 giây, thở ra 8 giây.",
    ),
)


@router.get("/resources", response_model=CrisisResourcesResponse)
async def get_crisis_resources():
    """US-023: Return crisis support resources (hotline + breathing exercise).

    No authentication required — accessible without login.
    """
    return _RESOURCES
