from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.goals import Goal, SEVERITY_SUGGESTIONS


async def update_user_goals(db: AsyncSession, user: User, goals: list[Goal]) -> User:
    user.goals = [g.value for g in goals]
    await db.flush()
    return user


def suggest_goals(severity: str) -> list[str]:
    return [g.value for g in SEVERITY_SUGGESTIONS.get(severity, [])]
