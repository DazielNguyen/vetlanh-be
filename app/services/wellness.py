from datetime import date

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wellness import WellnessChecklistCompletion
from app.schemas.wellness import WellnessChecklistItem, WellnessChecklistResponse

_STATIC_ITEMS: list[tuple[str, str, str]] = [
    ("morning-water", "Uống đủ nước", "Bắt đầu ngày mới với một ly nước"),
    ("short-walk", "Đi bộ ngắn", "Ít nhất 10 phút trong ngày"),
    ("deep-breath", "Thở sâu", "3 chu kỳ thở sâu để thư giãn"),
    ("gratitude", "Viết ơn", "Một điều bạn biết ơn hôm nay"),
    ("screen-break", "Nghỉ màn hình", "Tránh xa điện thoại 30 phút"),
    ("sleep-prep", "Chuẩn bị giấc ngủ", "Tắt đèn trước 23h"),
]


async def get_wellness_checklist(
    db: AsyncSession, user_id: int, target_date: date
) -> WellnessChecklistResponse:
    result = await db.execute(
        select(WellnessChecklistCompletion.item_key).where(
            WellnessChecklistCompletion.user_id == user_id,
            WellnessChecklistCompletion.date == target_date,
        )
    )
    completed_keys = set(result.scalars().all())

    items = [
        WellnessChecklistItem(
            id=key,
            title=title,
            subtitle=subtitle,
            completed=key in completed_keys,
        )
        for key, title, subtitle in _STATIC_ITEMS
    ]
    return WellnessChecklistResponse(date=target_date, items=items)


async def update_wellness_item(
    db: AsyncSession, user_id: int, item_id: str, completed: bool, target_date: date
) -> WellnessChecklistItem:
    item_def = next(
        ((k, t, s) for k, t, s in _STATIC_ITEMS if k == item_id),
        None,
    )
    if item_def is None:
        raise HTTPException(status_code=404, detail="Wellness item not found")

    key, title, subtitle = item_def

    if completed:
        stmt = pg_insert(WellnessChecklistCompletion).values(
            user_id=user_id, item_key=key, date=target_date
        ).on_conflict_do_nothing(constraint="uq_wellness_user_item_date")
        await db.execute(stmt)
    else:
        await db.execute(
            delete(WellnessChecklistCompletion).where(
                WellnessChecklistCompletion.user_id == user_id,
                WellnessChecklistCompletion.item_key == key,
                WellnessChecklistCompletion.date == target_date,
            )
        )
    await db.flush()

    return WellnessChecklistItem(id=key, title=title, subtitle=subtitle, completed=completed)
