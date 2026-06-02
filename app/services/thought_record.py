from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.thought_record import ThoughtRecord
from app.schemas.thought_record import ThoughtRecordCreate, ThoughtRecordUpdate


async def create_record(
    db: AsyncSession, user_id: int, payload: ThoughtRecordCreate
) -> ThoughtRecord:
    record = ThoughtRecord(
        user_id=user_id,
        situation=payload.situation,
        automatic_thought=payload.automatic_thought,
        emotion=payload.emotion,
        evidence=payload.evidence,
        alternative_thought=payload.alternative_thought,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def list_records(
    db: AsyncSession,
    user_id: int,
    limit: int = 20,
    offset: int = 0,
) -> list[ThoughtRecord]:
    result = await db.execute(
        select(ThoughtRecord)
        .where(ThoughtRecord.user_id == user_id)
        .order_by(ThoughtRecord.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_record(
    db: AsyncSession, user_id: int, record_id: int
) -> ThoughtRecord | None:
    result = await db.execute(
        select(ThoughtRecord).where(
            ThoughtRecord.id == record_id,
            ThoughtRecord.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def update_record(
    db: AsyncSession, user_id: int, record_id: int, payload: ThoughtRecordUpdate
) -> ThoughtRecord | None:
    record = await get_record(db, user_id, record_id)
    if record is None:
        return None
    for field in payload.model_fields_set:
        setattr(record, field, getattr(payload, field))
    await db.flush()
    await db.refresh(record)
    return record


async def delete_record(db: AsyncSession, user_id: int, record_id: int) -> bool:
    record = await get_record(db, user_id, record_id)
    if record is None:
        return False
    await db.delete(record)
    await db.flush()
    return True
