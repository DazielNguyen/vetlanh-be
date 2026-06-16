from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

VALID_CATEGORIES = {"healing", "psychology", "research", "lifestyle"}


class ArticleCreate(BaseModel):
    id: str = Field(min_length=1, max_length=255)
    title: str
    excerpt: Optional[str] = None
    content: Optional[str] = None
    category: str
    read_minutes: Optional[int] = Field(default=None, ge=0)
    cover_url: Optional[str] = None
    cloudinary_public_id: Optional[str] = None
    is_published: bool = False
    sort_order: int = Field(default=0, ge=0)


class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    excerpt: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    read_minutes: Optional[int] = Field(default=None, ge=0)
    cover_url: Optional[str] = None
    cloudinary_public_id: Optional[str] = None
    is_published: Optional[bool] = None
    sort_order: Optional[int] = Field(default=None, ge=0)
    published_at: Optional[datetime] = None


class ArticleResponse(BaseModel):
    id: str
    title: str
    excerpt: Optional[str]
    content: Optional[str]
    category: str
    read_minutes: Optional[int]
    cover_url: Optional[str]
    cloudinary_public_id: Optional[str]
    is_published: bool
    sort_order: int
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
