from typing import Literal

from pydantic import BaseModel


class HealingTask(BaseModel):
    id: str
    title: str
    subtitle: str
    progress_pct: int  # 0–100
    status: Literal["active", "locked", "upcoming"]
    unlock_label: str | None = None


class HealingPathResponse(BaseModel):
    tasks: list[HealingTask]


class UserStatsResponse(BaseModel):
    exercises_completed: int
    streak_days: int
