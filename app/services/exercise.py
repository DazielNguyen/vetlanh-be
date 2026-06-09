from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import UserExerciseLog
from app.schemas.exercise import (
    BreathingPhase,
    ExerciseCategory,
    ExerciseLogCreate,
    ExerciseLogUpdate,
    ExerciseResponse,
    ExerciseStep,
    MoodFilter,
)

# ---------------------------------------------------------------------------
# Static exercise catalogue
# US-016: breathing (box, 4-7-8, coherent)
# US-017: grounding 5-4-3-2-1
# US-018: meditation audio (5/10/15 min variants)
# ---------------------------------------------------------------------------

_EXERCISES: list[ExerciseResponse] = [
    # --- US-016: Breathing ---
    ExerciseResponse(
        slug="box-breathing",
        title="Box Breathing (4-4-4-4)",
        description="Kỹ thuật thở hộp giúp cân bằng hệ thần kinh, giảm căng thẳng tức thì.",
        category=ExerciseCategory.breathing,
        duration_minutes=4,
        mood_tags=[MoodFilter.anxious, MoodFilter.angry],
        phases=[
            BreathingPhase(label="Hít vào", seconds=4),
            BreathingPhase(label="Giữ", seconds=4),
            BreathingPhase(label="Thở ra", seconds=4),
            BreathingPhase(label="Giữ", seconds=4),
        ],
    ),
    ExerciseResponse(
        slug="breathing-4-7-8",
        title="Thở 4-7-8",
        description="Kỹ thuật thở giúp kích hoạt phản ứng thư giãn tự nhiên, lý tưởng trước khi ngủ.",
        category=ExerciseCategory.breathing,
        duration_minutes=5,
        mood_tags=[MoodFilter.anxious, MoodFilter.cant_sleep],
        phases=[
            BreathingPhase(label="Hít vào", seconds=4),
            BreathingPhase(label="Giữ", seconds=7),
            BreathingPhase(label="Thở ra", seconds=8),
        ],
    ),
    ExerciseResponse(
        slug="coherent-breathing",
        title="Coherent Breathing",
        description="Thở đều 5 giây vào – 5 giây ra, đồng bộ hệ tim mạch và thần kinh.",
        category=ExerciseCategory.breathing,
        duration_minutes=5,
        mood_tags=[MoodFilter.anxious, MoodFilter.sad, MoodFilter.need_energy],
        phases=[
            BreathingPhase(label="Hít vào", seconds=5),
            BreathingPhase(label="Thở ra", seconds=5),
        ],
    ),
    # --- US-017: Grounding ---
    ExerciseResponse(
        slug="grounding-54321",
        title="Grounding 5-4-3-2-1",
        description="Kỹ thuật đưa bản thân trở về hiện tại ngay lập tức bằng 5 giác quan.",
        category=ExerciseCategory.grounding,
        duration_minutes=5,
        mood_tags=[MoodFilter.anxious, MoodFilter.angry],
        steps=[
            ExerciseStep(
                order=1,
                instruction="Hãy nhìn xung quanh và liệt kê 5 thứ bạn có thể nhìn thấy.",
                input_prompt="5 thứ tôi nhìn thấy...",
            ),
            ExerciseStep(
                order=2,
                instruction="Chạm vào xung quanh và liệt kê 4 thứ bạn có thể cảm nhận được.",
                input_prompt="4 thứ tôi chạm được...",
            ),
            ExerciseStep(
                order=3,
                instruction="Lắng nghe và liệt kê 3 âm thanh bạn đang nghe.",
                input_prompt="3 âm thanh tôi nghe thấy...",
            ),
            ExerciseStep(
                order=4,
                instruction="Hít vào và liệt kê 2 mùi bạn ngửi được (hoặc mùi yêu thích).",
                input_prompt="2 mùi tôi ngửi được...",
            ),
            ExerciseStep(
                order=5,
                instruction="Liệt kê 1 thứ bạn có thể nếm hoặc vị bạn đang cảm nhận.",
                input_prompt="1 thứ tôi nếm được...",
            ),
        ],
    ),
    # --- US-018: Meditation ---
    ExerciseResponse(
        slug="meditation-body-scan",
        title="Body Scan",
        description="Quét toàn thân để nhận biết và thả lỏng từng vùng căng thẳng.",
        category=ExerciseCategory.meditation,
        duration_minutes=10,
        mood_tags=[MoodFilter.anxious, MoodFilter.cant_sleep, MoodFilter.sad],
        audio_url="/static/audio/body-scan.mp3",
        audio_options_minutes=[5, 10, 15],
    ),
    ExerciseResponse(
        slug="meditation-loving-kindness",
        title="Loving-Kindness",
        description="Nuôi dưỡng lòng từ bi với bản thân và người xung quanh.",
        category=ExerciseCategory.meditation,
        duration_minutes=10,
        mood_tags=[MoodFilter.sad, MoodFilter.angry],
        audio_url="/static/audio/loving-kindness.mp3",
        audio_options_minutes=[5, 10, 15],
    ),
    ExerciseResponse(
        slug="meditation-breath",
        title="Thiền Hơi Thở",
        description="Tập trung vào hơi thở để làm yên tâm trí đang bận rộn.",
        category=ExerciseCategory.meditation,
        duration_minutes=10,
        mood_tags=[MoodFilter.anxious, MoodFilter.need_energy],
        audio_url="/static/audio/breath-meditation.mp3",
        audio_options_minutes=[5, 10, 15],
    ),
    ExerciseResponse(
        slug="meditation-sleep",
        title="Ngủ Ngon",
        description="Thiền nhẹ nhàng giúp cơ thể và tâm trí sẵn sàng cho giấc ngủ sâu.",
        category=ExerciseCategory.meditation,
        duration_minutes=15,
        mood_tags=[MoodFilter.cant_sleep, MoodFilter.anxious],
        audio_url="/static/audio/sleep-meditation.mp3",
        audio_options_minutes=[5, 10, 15],
    ),
    ExerciseResponse(
        slug="meditation-anxiety",
        title="Giảm Lo Âu",
        description="Thiền có hướng dẫn đặc biệt cho những lúc lo lắng quá mức.",
        category=ExerciseCategory.meditation,
        duration_minutes=10,
        mood_tags=[MoodFilter.anxious],
        audio_url="/static/audio/anxiety-relief.mp3",
        audio_options_minutes=[5, 10, 15],
    ),
    # --- US-021: Progressive Muscle Relaxation ---
    ExerciseResponse(
        slug="pmr-7-groups",
        title="Thư Giãn Cơ Tuần Tiến (PMR)",
        description="Căng và thả lỏng từng nhóm cơ để giải phóng căng thẳng tích tụ trong cơ thể.",
        category=ExerciseCategory.relaxation,
        duration_minutes=14,
        mood_tags=[MoodFilter.anxious, MoodFilter.angry],
        steps=[
            ExerciseStep(
                order=1,
                instruction="Nắm chặt hai nắm tay, giữ trong 7 giây rồi từ từ thả lỏng hoàn toàn.",
                tense_seconds=7,
                release_seconds=30,
            ),
            ExerciseStep(
                order=2,
                instruction="Gập hai cánh tay lên, căng cơ bắp tay trong 7 giây rồi thả xuống nhẹ nhàng.",
                tense_seconds=7,
                release_seconds=30,
            ),
            ExerciseStep(
                order=3,
                instruction="Nhún vai lên sát tai, căng vai và cổ trong 7 giây rồi thả xuống.",
                tense_seconds=7,
                release_seconds=30,
            ),
            ExerciseStep(
                order=4,
                instruction="Nhăn mặt lại — cau mày, nhắm mắt, mím môi — giữ 7 giây rồi thả lỏng.",
                tense_seconds=7,
                release_seconds=30,
            ),
            ExerciseStep(
                order=5,
                instruction="Hít sâu và căng cơ bụng trong 7 giây, như thể bạn đang chuẩn bị chịu đòn, rồi thở ra và thả lỏng.",
                tense_seconds=7,
                release_seconds=30,
            ),
            ExerciseStep(
                order=6,
                instruction="Ép chặt hai đùi vào nhau và căng cơ đùi trong 7 giây rồi thả lỏng.",
                tense_seconds=7,
                release_seconds=30,
            ),
            ExerciseStep(
                order=7,
                instruction="Duỗi thẳng bàn chân và uốn cong các ngón chân xuống, giữ 7 giây rồi thả lỏng hoàn toàn.",
                tense_seconds=7,
                release_seconds=30,
            ),
        ],
    ),
]

# Fast lookups — built once at import time
_BY_SLUG: dict[str, ExerciseResponse] = {e.slug: e for e in _EXERCISES}

_BY_MOOD: dict[MoodFilter, list[ExerciseResponse]] = {
    mood: [e for e in _EXERCISES if mood in e.mood_tags]
    for mood in MoodFilter
}


# ---------------------------------------------------------------------------
# Query helpers — US-020: filter by mood_tag and/or category
# ---------------------------------------------------------------------------

def list_exercises(
    mood: MoodFilter | None = None,
    category: ExerciseCategory | None = None,
) -> list[ExerciseResponse]:
    if mood and not category:
        return _BY_MOOD.get(mood, [])
    return [
        e for e in _EXERCISES
        if (mood is None or mood in e.mood_tags)
        and (category is None or e.category == category)
    ]


def get_exercise(slug: str) -> ExerciseResponse | None:
    return _BY_SLUG.get(slug)


def get_recommended(mood: MoodFilter, limit: int = 3) -> list[ExerciseResponse]:
    return list_exercises(mood=mood)[:limit]


# ---------------------------------------------------------------------------
# DB operations — log completed exercises
# ---------------------------------------------------------------------------

async def log_exercise(
    db: AsyncSession,
    user_id: int,
    payload: ExerciseLogCreate,
) -> UserExerciseLog:
    if get_exercise(payload.exercise_slug) is None:
        raise ValueError(f"Unknown exercise slug: {payload.exercise_slug}")
    log = UserExerciseLog(
        user_id=user_id,
        exercise_slug=payload.exercise_slug,
        duration_seconds=payload.duration_seconds,
    )
    db.add(log)
    await db.flush()
    await db.refresh(log)
    return log


async def update_exercise_log(
    db: AsyncSession,
    log_id: int,
    user_id: int,
    payload: ExerciseLogUpdate,
) -> UserExerciseLog | None:
    result = await db.execute(
        select(UserExerciseLog).where(
            UserExerciseLog.id == log_id,
            UserExerciseLog.user_id == user_id,
        )
    )
    log = result.scalar_one_or_none()
    if log is None:
        return None
    log.post_session_feeling = payload.post_session_feeling
    await db.flush()
    return log


async def get_exercise_history(
    db: AsyncSession,
    user_id: int,
    limit: int = 20,
    offset: int = 0,
) -> list[UserExerciseLog]:
    result = await db.execute(
        select(UserExerciseLog)
        .where(UserExerciseLog.user_id == user_id)
        .order_by(UserExerciseLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()
