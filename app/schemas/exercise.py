from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ExerciseCategory(str, Enum):
    breathing = "breathing"
    grounding = "grounding"
    meditation = "meditation"
    cbt = "cbt"
    relaxation = "relaxation"


class MoodFilter(str, Enum):
    anxious = "anxious"
    sad = "sad"
    cant_sleep = "cant_sleep"
    need_energy = "need_energy"
    angry = "angry"


CATEGORY_LABELS: dict[ExerciseCategory, str] = {
    ExerciseCategory.breathing: "Hơi thở",
    ExerciseCategory.meditation: "Thiền",
    ExerciseCategory.grounding: "Hiện tại",
    ExerciseCategory.cbt: "CBT",
    ExerciseCategory.relaxation: "Thư giãn",
}

MOOD_FILTER_LABELS: dict[MoodFilter, str] = {
    MoodFilter.anxious: "Lo âu",
    MoodFilter.sad: "Buồn bã",
    MoodFilter.cant_sleep: "Mất ngủ",
    MoodFilter.need_energy: "Cần năng lượng",
    MoodFilter.angry: "Tức giận",
}

MOOD_FILTER_EMOJIS: dict[MoodFilter, str] = {
    MoodFilter.anxious: "😰",
    MoodFilter.sad: "😢",
    MoodFilter.cant_sleep: "🌙",
    MoodFilter.need_energy: "⚡",
    MoodFilter.angry: "😤",
}


class BreathingPhase(BaseModel):
    label: str
    seconds: int


class ExerciseStep(BaseModel):
    order: int
    instruction: str
    input_prompt: str | None = None  # for grounding — user types their answer
    tense_seconds: int | None = None   # PMR only: how long to tense the muscle group
    release_seconds: int | None = None  # PMR only: how long to hold the release


class ExerciseResponse(BaseModel):
    slug: str
    title: str
    description: str
    category: ExerciseCategory
    duration_minutes: int
    mood_tags: list[MoodFilter]
    # breathing exercises only
    phases: list[BreathingPhase] | None = None
    # grounding / meditation exercises
    steps: list[ExerciseStep] | None = None
    # meditation audio URL (served from CDN)
    audio_url: str | None = None
    audio_options_minutes: list[int] | None = None


class MoodFilterOption(BaseModel):
    key: str
    label: str
    emoji: str


class ExerciseLogCreate(BaseModel):
    exercise_slug: str = Field(min_length=1, max_length=100)
    duration_seconds: int = Field(ge=0, le=7200)


class PostSessionFeeling(str, Enum):
    much_better = "much_better"
    better = "better"
    same = "same"
    worse = "worse"


class ExerciseLogUpdate(BaseModel):
    post_session_feeling: PostSessionFeeling


class ExerciseLogResponse(BaseModel):
    id: int
    exercise_slug: str
    duration_seconds: int
    post_session_feeling: PostSessionFeeling | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
