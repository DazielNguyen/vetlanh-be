from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.schemas.assessment import Severity


class Goal(str, Enum):
    REDUCE_STRESS = "reduce_stress"
    BETTER_SLEEP = "better_sleep"
    CONTROL_ANXIETY = "control_anxiety"
    IMPROVE_MOOD = "improve_mood"
    INCREASE_ENERGY = "increase_energy"


GOAL_LABELS: dict[Goal, str] = {
    Goal.REDUCE_STRESS: "Giảm stress",
    Goal.BETTER_SLEEP: "Ngủ ngon hơn",
    Goal.CONTROL_ANXIETY: "Kiểm soát lo âu",
    Goal.IMPROVE_MOOD: "Cải thiện tâm trạng",
    Goal.INCREASE_ENERGY: "Tăng năng lượng",
}

SEVERITY_SUGGESTIONS: dict[str, list[Goal]] = {
    Severity.MINIMAL: [Goal.IMPROVE_MOOD, Goal.INCREASE_ENERGY],
    Severity.MILD: [Goal.REDUCE_STRESS, Goal.IMPROVE_MOOD, Goal.BETTER_SLEEP],
    Severity.MODERATE: [Goal.CONTROL_ANXIETY, Goal.REDUCE_STRESS, Goal.IMPROVE_MOOD],
    Severity.SEVERE: [Goal.CONTROL_ANXIETY, Goal.REDUCE_STRESS, Goal.BETTER_SLEEP],
}


class GoalsUpdateRequest(BaseModel):
    goals: list[Goal] = Field(..., min_length=1, max_length=3)

    @field_validator("goals")
    @classmethod
    def no_duplicates(cls, v: list[Goal]) -> list[Goal]:
        if len(v) != len(set(v)):
            raise ValueError("Duplicate goals are not allowed")
        return v
