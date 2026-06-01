from sqlalchemy.ext.asyncio import AsyncSession


async def update_daily_mood(db: AsyncSession, user_id: int, sentiment: str) -> None:
    """Update the user's daily mood score based on conversation sentiment.

    This is a placeholder — wired up when Epic E3 (Mood Tracker) is implemented.
    E3 will introduce the DailyMoodScore model and aggregate sentiment into a score.
    """
    pass
