from datetime import date

from pydantic import BaseModel


class WellnessChecklistItem(BaseModel):
    id: str
    title: str
    subtitle: str
    completed: bool


class WellnessChecklistResponse(BaseModel):
    date: date
    items: list[WellnessChecklistItem]


class WellnessItemUpdate(BaseModel):
    completed: bool
