from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.reflection import ReflectionFeedResponse, ReflectionType
from app.services.reflection import _decode_cursor, list_reflections

router = APIRouter(prefix="/reflections", tags=["reflections"])


@router.get(
    "",
    response_model=ReflectionFeedResponse,
)
async def get_reflections(
    reflection_type: ReflectionType = Query(default=ReflectionType.ALL, alias="type"),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReflectionFeedResponse:
    if cursor is not None:
        try:
            _decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid cursor") from exc

    return await list_reflections(
        db,
        current_user.id,
        reflection_type=reflection_type,
        q=q,
        limit=limit,
        cursor=cursor,
    )
