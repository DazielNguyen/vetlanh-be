"""Schemas for US-027 — Streak badges."""

from pydantic import BaseModel


class BadgeOut(BaseModel):
    slug: str
    label: str
    milestone_days: int
    unlocked: bool
    # True only on the first response after the milestone is reached
    is_new: bool


class BadgesResponse(BaseModel):
    streak_days: int
    badges: list[BadgeOut]
