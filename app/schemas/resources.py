from typing import Literal

from pydantic import BaseModel


class ResourceItem(BaseModel):
    id: str
    title: str
    type: Literal["article", "audio", "video"]
    duration_label: str
    url: str | None = None
