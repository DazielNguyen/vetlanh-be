"""
Unit tests for Sprint 2 changes to the AI chatbot service.

Covers:
  - _pick_exercise_card — returns ExerciseCard on trigger keywords, None otherwise
  - _check_negative_streak — DB-mocked async query, streak logic
  - ExerciseCard / ExerciseStep — schema validation and serialisation
  - MessageResponse — sentiment field is optional, defaults to None
  - update_daily_mood — stub exists, is a coroutine, runs without error
"""

import inspect
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.chat import ExerciseCard, ExerciseStep, MessageResponse
from app.services.chat import _check_negative_streak, _pick_exercise_card
from app.services.mood import update_daily_mood


# ---------------------------------------------------------------------------
# Override autouse fixtures from the global conftest that require a real DB.
# These tests are pure unit tests — no live database or HTTP server needed.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_email():  # noqa: F811 — intentionally shadows conftest fixture
    """No-op override: these unit tests never send email."""
    yield


@pytest.fixture(autouse=True)
async def clean_db():  # noqa: F811 — intentionally shadows conftest fixture
    """No-op override: these unit tests do not touch the database."""
    yield


# ---------------------------------------------------------------------------
# _pick_exercise_card
# ---------------------------------------------------------------------------


class TestPickExerciseCard:
    def test_returns_card_on_bai_tap_tho(self):
        """'bài tập thở' is an explicit trigger keyword."""
        card = _pick_exercise_card("Mình có một bài tập thở ngắn cho bạn.")
        assert card is not None
        assert card.id == "box-breathing"

    def test_returns_card_on_hit_vao(self):
        """'hít vào' is an explicit trigger keyword."""
        card = _pick_exercise_card("Bạn hãy hít vào từ từ nhé.")
        assert card is not None
        assert card.id == "box-breathing"

    def test_returns_card_on_hit_tho(self):
        """'hít thở' is also in the trigger list."""
        card = _pick_exercise_card("Chúng ta hãy thực hiện bài hít thở nhé.")
        assert card is not None
        assert card.id == "box-breathing"

    def test_returns_card_on_tho_hop(self):
        """'thở hộp' maps to box-breathing."""
        card = _pick_exercise_card("Kỹ thuật thở hộp sẽ giúp bạn.")
        assert card is not None
        assert card.id == "box-breathing"

    def test_returns_card_on_tho_ra(self):
        """'thở ra' is a trigger keyword."""
        card = _pick_exercise_card("Bạn hãy thở ra từ từ qua miệng.")
        assert card is not None
        assert card.id == "box-breathing"

    def test_returns_card_keyword_uppercase(self):
        """Match is case-insensitive (lowercase comparison applied internally)."""
        card = _pick_exercise_card("BÀI TẬP THỞ rất hiệu quả.")
        assert card is not None
        assert card.id == "box-breathing"

    def test_returns_none_when_no_keyword(self):
        """Generic comforting text without exercise keywords returns None."""
        card = _pick_exercise_card("Mình hiểu bạn đang cảm thấy rất khó khăn.")
        assert card is None

    def test_returns_none_for_empty_string(self):
        card = _pick_exercise_card("")
        assert card is None

    def test_returned_card_has_steps(self):
        """Sanity-check: the returned card has at least one step."""
        card = _pick_exercise_card("bài tập thở")
        assert card is not None
        assert len(card.steps) > 0

    def test_returned_card_is_exercise_card_instance(self):
        card = _pick_exercise_card("hít vào")
        assert isinstance(card, ExerciseCard)


# ---------------------------------------------------------------------------
# _check_negative_streak
# ---------------------------------------------------------------------------


def _make_db_mock(rows: list[tuple]):
    """Return an AsyncSession-like mock whose execute returns the given rows."""
    result_mock = MagicMock()
    result_mock.all.return_value = rows

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    return db


class TestCheckNegativeStreak:
    async def test_returns_true_when_five_negatives(self):
        """Five most-recent sentiments all 'negative' → True."""
        rows = [("negative",)] * 5
        db = _make_db_mock(rows)
        assert await _check_negative_streak(db, conversation_id=1) is True

    async def test_returns_false_when_fewer_than_five(self):
        """Only 4 negative messages — threshold not yet reached → False."""
        rows = [("negative",)] * 4
        db = _make_db_mock(rows)
        assert await _check_negative_streak(db, conversation_id=1) is False

    async def test_returns_false_when_mixed_sentiments(self):
        """Four negatives and one neutral break the streak → False."""
        rows = [("negative",), ("negative",), ("neutral",), ("negative",), ("negative",)]
        db = _make_db_mock(rows)
        assert await _check_negative_streak(db, conversation_id=1) is False

    async def test_returns_false_when_positive_in_streak(self):
        """One positive in an otherwise negative streak → False."""
        rows = [("negative",), ("positive",), ("negative",), ("negative",), ("negative",)]
        db = _make_db_mock(rows)
        assert await _check_negative_streak(db, conversation_id=1) is False

    async def test_returns_false_when_no_messages(self):
        """No user messages with sentiment → False."""
        db = _make_db_mock([])
        assert await _check_negative_streak(db, conversation_id=99) is False

    async def test_returns_false_when_exactly_one_negative(self):
        """Single negative message is not a streak → False."""
        db = _make_db_mock([("negative",)])
        assert await _check_negative_streak(db, conversation_id=1) is False

    async def test_db_execute_called_once(self):
        """Confirms the function makes exactly one DB query."""
        db = _make_db_mock([("negative",)] * 5)
        await _check_negative_streak(db, conversation_id=7)
        db.execute.assert_called_once()

    async def test_returns_true_six_negatives(self):
        """More than threshold of negatives (DB limit=5 already enforced in query)
        but mock returns 5 rows → True."""
        rows = [("negative",)] * 5
        db = _make_db_mock(rows)
        assert await _check_negative_streak(db, conversation_id=2) is True


# ---------------------------------------------------------------------------
# ExerciseStep schema
# ---------------------------------------------------------------------------


class TestExerciseStep:
    def test_valid_step_with_duration(self):
        step = ExerciseStep(order=1, instruction="Hít vào", duration_seconds=4)
        assert step.order == 1
        assert step.instruction == "Hít vào"
        assert step.duration_seconds == 4

    def test_duration_seconds_is_optional(self):
        """duration_seconds defaults to None when omitted."""
        step = ExerciseStep(order=5, instruction="Lặp lại")
        assert step.duration_seconds is None

    def test_duration_seconds_explicit_none(self):
        step = ExerciseStep(order=5, instruction="Lặp lại", duration_seconds=None)
        assert step.duration_seconds is None

    def test_serialises_to_dict(self):
        step = ExerciseStep(order=1, instruction="Hít vào", duration_seconds=4)
        d = step.model_dump()
        assert d == {"order": 1, "instruction": "Hít vào", "duration_seconds": 4}

    def test_serialises_none_duration(self):
        step = ExerciseStep(order=5, instruction="Lặp lại", duration_seconds=None)
        d = step.model_dump()
        assert d["duration_seconds"] is None


# ---------------------------------------------------------------------------
# ExerciseCard schema
# ---------------------------------------------------------------------------


class TestExerciseCard:
    def _make_card(self) -> ExerciseCard:
        return ExerciseCard(
            id="box-breathing",
            title="Thở Hộp",
            description="Kỹ thuật thở 4-4-4-4.",
            steps=[
                ExerciseStep(order=1, instruction="Hít vào", duration_seconds=4),
                ExerciseStep(order=2, instruction="Giữ hơi thở", duration_seconds=4),
                ExerciseStep(order=3, instruction="Thở ra", duration_seconds=4),
                ExerciseStep(order=4, instruction="Giữ trống phổi", duration_seconds=4),
                ExerciseStep(order=5, instruction="Lặp lại 4 lần", duration_seconds=None),
            ],
        )

    def test_valid_card_fields(self):
        card = self._make_card()
        assert card.id == "box-breathing"
        assert card.title == "Thở Hộp"
        assert len(card.steps) == 5

    def test_card_serialises_to_dict(self):
        card = self._make_card()
        d = card.model_dump()
        assert d["id"] == "box-breathing"
        assert isinstance(d["steps"], list)
        assert len(d["steps"]) == 5

    def test_last_step_has_none_duration(self):
        card = self._make_card()
        last_step = card.steps[-1]
        assert last_step.duration_seconds is None

    def test_card_steps_have_correct_orders(self):
        card = self._make_card()
        orders = [s.order for s in card.steps]
        assert orders == [1, 2, 3, 4, 5]

    def test_card_model_dump_includes_steps_duration(self):
        """Ensure nested steps serialise correctly including None values."""
        card = self._make_card()
        d = card.model_dump()
        last = d["steps"][-1]
        assert last["duration_seconds"] is None
        assert d["steps"][0]["duration_seconds"] == 4


# ---------------------------------------------------------------------------
# MessageResponse schema — sentiment field
# ---------------------------------------------------------------------------


class TestMessageResponseSchema:
    def _base_kwargs(self) -> dict:
        return {
            "id": 1,
            "role": "user",
            "content": "Tôi cảm thấy mệt mỏi.",
            "created_at": datetime(2026, 6, 1, 12, 0, 0),
        }

    def test_sentiment_defaults_to_none(self):
        msg = MessageResponse(**self._base_kwargs())
        assert msg.sentiment is None

    def test_sentiment_accepts_negative(self):
        msg = MessageResponse(**self._base_kwargs(), sentiment="negative")
        assert msg.sentiment == "negative"

    def test_sentiment_accepts_positive(self):
        msg = MessageResponse(**self._base_kwargs(), sentiment="positive")
        assert msg.sentiment == "positive"

    def test_sentiment_accepts_neutral(self):
        msg = MessageResponse(**self._base_kwargs(), sentiment="neutral")
        assert msg.sentiment == "neutral"

    def test_sentiment_accepts_explicit_none(self):
        msg = MessageResponse(**self._base_kwargs(), sentiment=None)
        assert msg.sentiment is None

    def test_serialises_with_null_sentiment(self):
        msg = MessageResponse(**self._base_kwargs())
        d = msg.model_dump()
        assert "sentiment" in d
        assert d["sentiment"] is None

    def test_serialises_with_sentiment_value(self):
        msg = MessageResponse(**self._base_kwargs(), sentiment="negative")
        d = msg.model_dump()
        assert d["sentiment"] == "negative"


# ---------------------------------------------------------------------------
# update_daily_mood — stub contract
# ---------------------------------------------------------------------------


class TestUpdateDailyMood:
    def test_is_coroutine_function(self):
        """update_daily_mood must be declared async (is a coroutine function)."""
        assert inspect.iscoroutinefunction(update_daily_mood)

    async def test_runs_without_error_positive(self):
        """Calling the stub with any sentiment must not raise."""
        db = AsyncMock()
        await update_daily_mood(db, user_id=1, sentiment="positive")

    async def test_runs_without_error_negative(self):
        db = AsyncMock()
        await update_daily_mood(db, user_id=2, sentiment="negative")

    async def test_runs_without_error_neutral(self):
        db = AsyncMock()
        await update_daily_mood(db, user_id=3, sentiment="neutral")

    async def test_returns_none(self):
        """Stub must return None (no-op)."""
        db = AsyncMock()
        result = await update_daily_mood(db, user_id=1, sentiment="neutral")
        assert result is None

    async def test_does_not_call_db(self):
        """Current stub must not touch the DB at all."""
        db = AsyncMock()
        await update_daily_mood(db, user_id=1, sentiment="positive")
        db.execute.assert_not_called()
        db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# _analyze_sentiment — mocked Bedrock Converse call
# ---------------------------------------------------------------------------


class TestAnalyzeSentiment:
    """Tests for _analyze_sentiment with mocked Bedrock Converse API."""

    def _mock_session(self, text: str):
        """Return a mock aioboto3 session whose converse() returns the given text."""
        response = {"output": {"message": {"content": [{"text": text}]}}}
        mock_client = AsyncMock()
        mock_client.converse = AsyncMock(return_value=response)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_ctx)
        return mock_session

    async def test_returns_positive(self):
        from app.services.chat import _analyze_sentiment

        with patch("app.services.chat._session", self._mock_session("positive")):
            result = await _analyze_sentiment("Hôm nay tôi rất vui!")
        assert result == "positive"

    async def test_returns_negative(self):
        from app.services.chat import _analyze_sentiment

        with patch("app.services.chat._session", self._mock_session("negative")):
            result = await _analyze_sentiment("Tôi cảm thấy rất buồn.")
        assert result == "negative"

    async def test_returns_neutral(self):
        from app.services.chat import _analyze_sentiment

        with patch("app.services.chat._session", self._mock_session("neutral")):
            result = await _analyze_sentiment("Hôm nay trời bình thường.")
        assert result == "neutral"

    async def test_fallback_to_neutral_on_unexpected_value(self):
        """When Bedrock returns an unrecognised word, fall back to 'neutral'."""
        from app.services.chat import _analyze_sentiment

        with patch("app.services.chat._session", self._mock_session("unsure")):
            result = await _analyze_sentiment("Some text.")
        assert result == "neutral"

    async def test_strips_whitespace_from_response(self):
        """Response with surrounding spaces/newlines is still recognised."""
        from app.services.chat import _analyze_sentiment

        with patch("app.services.chat._session", self._mock_session("  Positive  ")):
            result = await _analyze_sentiment("Tuyệt vời quá!")
        assert result == "positive"
