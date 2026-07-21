from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.reflection import ReflectionType
from app.services.reflection import (
    TYPE_RANK,
    _decode_cursor,
    _encode_cursor,
    _map_journal,
    _map_thought_record,
    _plain_text,
    list_reflections,
)

NOW = datetime(2026, 7, 21, 8, 40, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
async def clean_db():
    yield


def _journal(**overrides):
    values = {
        "id": 7,
        "title": "Một ngày nhẹ nhàng",
        "content": "Hôm nay mình ổn hơn.",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _thought_record(**overrides):
    values = {
        "id": 9,
        "situation": "Cuộc họp sáng nay",
        "automatic_thought": "Mọi người không hài lòng với mình",
        "emotion": "Lo lắng, 70%",
        "evidence": "Sếp hỏi lại hai lần",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_plain_text_removes_markup_decodes_entities_and_normalizes_whitespace():
    assert _plain_text("<p>Hello &amp;  <strong>world</strong></p>\n next") == (
        "Hello & world next"
    )


def test_journal_mapping_uses_fallback_title_and_truncates_preview():
    item = _map_journal(_journal(title=None, content="<p>" + "á" * 170 + "</p>"))

    assert item.id == "journal:7"
    assert item.resource_id == "7"
    assert item.type is ReflectionType.JOURNAL
    assert item.title == "Một ghi chép nhỏ"
    assert item.preview == "á" * 160
    assert item.emotion is None


def test_thought_record_mapping_truncates_title_and_preview():
    item = _map_thought_record(
        _thought_record(situation="s" * 90, automatic_thought="t" * 170)
    )

    assert item.id == "thought_record:9"
    assert item.resource_id == "9"
    assert item.type is ReflectionType.THOUGHT_RECORD
    assert item.title == "s" * 80
    assert item.preview == "t" * 160
    assert item.emotion == "Lo lắng, 70%"


def test_cursor_round_trip_preserves_complete_sort_key():
    item = _map_journal(_journal())

    assert _decode_cursor(_encode_cursor(item)) == (
        NOW,
        TYPE_RANK[ReflectionType.JOURNAL],
        7,
    )


@pytest.mark.parametrize(
    "cursor",
    ["", "not-base64", "e30", "eyJ2IjoyfQ"],
)
def test_decode_cursor_rejects_malformed_values(cursor):
    with pytest.raises(ValueError, match="Invalid cursor"):
        _decode_cursor(cursor)


def _scalar_result(values):
    scalars = MagicMock()
    scalars.all.return_value = values
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


async def test_list_reflections_queries_both_sources_with_user_scope():
    db = AsyncMock()
    db.execute.side_effect = [_scalar_result([]), _scalar_result([])]

    result = await list_reflections(db, user_id=42)

    assert result.items == []
    assert result.next_cursor is None
    assert db.execute.await_count == 2
    for call in db.execute.await_args_list:
        compiled = call.args[0].compile()
        assert 42 in compiled.params.values()


async def test_type_filter_queries_only_selected_source():
    db = AsyncMock()
    db.execute.return_value = _scalar_result([_journal()])

    result = await list_reflections(
        db, user_id=42, reflection_type=ReflectionType.JOURNAL
    )

    assert [item.id for item in result.items] == ["journal:7"]
    db.execute.assert_awaited_once()


async def test_search_is_trimmed_case_insensitive_and_covers_visible_fields():
    journals = [
        _journal(id=1, title="Khác", content="Mình thấy LO LẮNG"),
        _journal(id=2, title="Không khớp", content="Bình thường"),
    ]
    thoughts = [
        _thought_record(id=3, evidence="Có bằng chứng lo lắng"),
        _thought_record(
            id=4,
            situation="Ổn",
            automatic_thought="Mọi việc bình thường",
            emotion="Bình tĩnh",
            evidence="Không liên quan",
        ),
    ]
    db = AsyncMock()
    db.execute.side_effect = [_scalar_result(journals), _scalar_result(thoughts)]

    result = await list_reflections(db, user_id=42, q="  lo lắng  ")

    assert {item.id for item in result.items} == {"journal:1", "thought_record:3"}


async def test_empty_search_is_ignored():
    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_result([_journal(id=1)]),
        _scalar_result([_thought_record(id=2)]),
    ]

    result = await list_reflections(db, user_id=42, q="   ")

    assert len(result.items) == 2


async def test_global_order_and_cursor_pages_have_no_duplicates():
    newer = NOW.replace(minute=50)
    older = NOW.replace(minute=30)
    journals = [
        _journal(id=1, created_at=NOW),
        _journal(id=2, created_at=older),
    ]
    thoughts = [
        _thought_record(id=3, created_at=newer),
        _thought_record(id=4, created_at=NOW),
    ]

    first_db = AsyncMock()
    first_db.execute.side_effect = [
        _scalar_result(journals),
        _scalar_result(thoughts),
    ]
    first = await list_reflections(first_db, user_id=42, limit=2)

    assert [item.id for item in first.items] == [
        "thought_record:3",
        "thought_record:4",
    ]
    assert first.next_cursor is not None

    second_db = AsyncMock()
    second_db.execute.side_effect = [
        _scalar_result(journals),
        _scalar_result(thoughts),
    ]
    second = await list_reflections(
        second_db, user_id=42, limit=2, cursor=first.next_cursor
    )

    assert [item.id for item in second.items] == ["journal:1", "journal:2"]
    assert second.next_cursor is None
    assert set(item.id for item in first.items).isdisjoint(
        item.id for item in second.items
    )
