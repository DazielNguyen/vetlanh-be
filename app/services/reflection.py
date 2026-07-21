import base64
import json
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import JournalEntry
from app.models.thought_record import ThoughtRecord
from app.schemas.reflection import (
    ReflectionFeedResponse,
    ReflectionItem,
    ReflectionType,
)

TYPE_RANK = {
    ReflectionType.JOURNAL: 1,
    ReflectionType.THOUGHT_RECORD: 2,
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    return " ".join(unescape("".join(parser.parts)).split())


def _map_journal(entry) -> ReflectionItem:
    return ReflectionItem(
        id=f"journal:{entry.id}",
        resource_id=str(entry.id),
        type=ReflectionType.JOURNAL,
        title=entry.title if entry.title is not None else "Một ghi chép nhỏ",
        preview=_plain_text(entry.content)[:160],
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _map_thought_record(record) -> ReflectionItem:
    return ReflectionItem(
        id=f"thought_record:{record.id}",
        resource_id=str(record.id),
        type=ReflectionType.THOUGHT_RECORD,
        title=record.situation[:80],
        preview=_plain_text(record.automatic_thought)[:160],
        emotion=record.emotion,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _cursor_key(item: ReflectionItem) -> tuple[datetime, int, int]:
    created_at = item.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return (
        created_at.astimezone(timezone.utc),
        TYPE_RANK[item.type],
        int(item.resource_id),
    )


def _encode_cursor(item: ReflectionItem) -> str:
    created_at, rank, resource_id = _cursor_key(item)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    payload = {
        "v": 1,
        "created_at": created_at.astimezone(timezone.utc).isoformat(),
        "type_rank": rank,
        "resource_id": resource_id,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, int, int]:
    try:
        if not value:
            raise ValueError
        padding = "=" * (-len(value) % 4)
        payload = json.loads(
            base64.b64decode(value + padding, altchars=b"-_", validate=True)
        )
        if set(payload) != {"v", "created_at", "type_rank", "resource_id"}:
            raise ValueError
        if payload["v"] != 1 or payload["type_rank"] not in TYPE_RANK.values():
            raise ValueError
        if not isinstance(payload["resource_id"], int) or payload["resource_id"] <= 0:
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None:
            raise ValueError
        return (
            created_at.astimezone(timezone.utc),
            payload["type_rank"],
            payload["resource_id"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid cursor") from exc


def _contains_query(values: list[str | None], query: str) -> bool:
    return any(query in (value or "").casefold() for value in values)


async def list_reflections(
    db: AsyncSession,
    user_id: int,
    reflection_type: ReflectionType = ReflectionType.ALL,
    q: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> ReflectionFeedResponse:
    items: list[ReflectionItem] = []
    query = (q or "").strip().casefold()

    if reflection_type in (ReflectionType.ALL, ReflectionType.JOURNAL):
        result = await db.execute(
            select(JournalEntry).where(JournalEntry.user_id == user_id)
        )
        journals = result.scalars().all()
        for entry in journals:
            if not query or _contains_query([entry.title, entry.content], query):
                items.append(_map_journal(entry))

    if reflection_type in (ReflectionType.ALL, ReflectionType.THOUGHT_RECORD):
        result = await db.execute(
            select(ThoughtRecord).where(ThoughtRecord.user_id == user_id)
        )
        records = result.scalars().all()
        for record in records:
            if not query or _contains_query(
                [
                    record.situation,
                    record.automatic_thought,
                    record.emotion,
                    record.evidence,
                ],
                query,
            ):
                items.append(_map_thought_record(record))

    items.sort(key=_cursor_key, reverse=True)
    if cursor is not None:
        boundary = _decode_cursor(cursor)
        items = [item for item in items if _cursor_key(item) < boundary]

    has_more = len(items) > limit
    page = items[:limit]
    next_cursor = _encode_cursor(page[-1]) if has_more else None
    return ReflectionFeedResponse(items=page, next_cursor=next_cursor)
