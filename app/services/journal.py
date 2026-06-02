from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import JournalEntry
from app.schemas.journal import JournalEntryCreate, JournalEntryUpdate


def _count_words(text: str) -> int:
    return len(text.split()) if text.strip() else 0


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def create_entry(
    db: AsyncSession, user_id: int, payload: JournalEntryCreate
) -> JournalEntry:
    entry = JournalEntry(
        user_id=user_id,
        title=payload.title,
        content=payload.content,
        word_count=_count_words(payload.content),
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


async def list_entries(
    db: AsyncSession,
    user_id: int,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[JournalEntry]:
    query = (
        select(JournalEntry)
        .where(JournalEntry.user_id == user_id)
        .order_by(JournalEntry.created_at.desc())
    )
    if q:
        pattern = f"%{_escape_like(q)}%"
        # content column is Fernet-encrypted — ILIKE on ciphertext never matches.
        # Search is title-only until a searchable encrypted index is added.
        query = query.where(JournalEntry.title.ilike(pattern, escape="\\"))
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_entry(db: AsyncSession, user_id: int, entry_id: int) -> JournalEntry | None:
    result = await db.execute(
        select(JournalEntry).where(
            JournalEntry.id == entry_id,
            JournalEntry.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def update_entry(
    db: AsyncSession, user_id: int, entry_id: int, payload: JournalEntryUpdate
) -> JournalEntry | None:
    entry = await get_entry(db, user_id, entry_id)
    if entry is None:
        return None
    if "title" in payload.model_fields_set:
        entry.title = payload.title
    if payload.content is not None:
        entry.content = payload.content
        entry.word_count = _count_words(payload.content)
    await db.flush()
    await db.refresh(entry)
    return entry


async def delete_entry(db: AsyncSession, user_id: int, entry_id: int) -> bool:
    entry = await get_entry(db, user_id, entry_id)
    if entry is None:
        return False
    await db.delete(entry)
    await db.flush()
    return True
