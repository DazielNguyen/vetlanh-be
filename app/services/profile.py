from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.profile import ProfileUpdateRequest


async def update_profile(db: AsyncSession, user: User, payload: ProfileUpdateRequest) -> User:
    """Apply only the fields the caller explicitly provided (PATCH semantics).

    Pydantic's model_fields_set contains only the keys present in the request
    body — fields the client omitted are not in this set and are left unchanged.
    This prevents an accidental null-overwrite when a field is simply not sent.
    """
    for field in payload.model_fields_set:
        value = getattr(payload, field)
        # AnyHttpUrl serialises to a Url object; store the plain string in the DB
        if field == "avatar_url" and value is not None:
            value = str(value)
        setattr(user, field, value)

    await db.flush()
    return user
