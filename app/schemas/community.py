from pydantic import BaseModel


class CommunityFeaturedResponse(BaseModel):
    message: str
    author_display: str
    active_users_count: int
