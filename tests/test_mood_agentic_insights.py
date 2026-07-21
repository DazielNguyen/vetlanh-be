"""Unit coverage for the safety and versioning boundaries of mood reflections."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.mood import MoodAnalysis
from app.schemas.mood import AgentMoodOutput, MoodNextAction
from app.services.crisis import CrisisLevel
from app.services.mood_analysis import (
    _confidence_and_evidence,
    _generate_with_retry,
    _is_current_job,
    _safe_action,
    _validate_agent_text,
    process_analysis,
)


TEST_EMAIL_DOMAIN = "test.vetlanh"
_TODAY = datetime.now(tz=timezone.utc).date().isoformat()


async def _register_and_login(client: AsyncClient, email: str) -> str:
    captured = []

    async def capture(*args, **kwargs):
        captured.append(args)

    with patch("app.api.v1.endpoints.auth.send_verification_email", side_effect=capture):
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass1"},
        )
    await client.get(f"/api/v1/auth/verify?token={captured[0][1]}")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "securepass1"},
    )
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _analysis_id_for_entry(entry_id: int) -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MoodAnalysis.id)
            .where(MoodAnalysis.entry_id == entry_id)
            .order_by(MoodAnalysis.id.desc())
            .limit(1)
        )
        value = result.scalar_one()
        return value


class TestMoodAgenticBoundaries:
    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    @staticmethod
    def _entry(*, mood=2, energy="low", note=None, updated_at=None):
        entry = MagicMock()
        entry.id = 10
        entry.mood = mood
        entry.energy = energy
        entry.note = note
        entry.factors = []
        entry.updated_at = updated_at or datetime.now(tz=timezone.utc)
        entry.created_at = entry.updated_at
        return entry

    def test_weak_statistics_never_expose_quantitative_evidence(self):
        statistics = {
            "factor_correlations": [
                {"factor": "sleep", "sample_size": 3, "total_entries": 9, "delta": -0.4}
            ]
        }
        assert _confidence_and_evidence(statistics) == ("low", None)

    def test_medium_statistics_use_backend_generated_evidence(self):
        statistics = {
            "factor_correlations": [
                {"factor": "sleep", "sample_size": 4, "total_entries": 12, "delta": -0.7}
            ]
        }
        confidence, evidence = _confidence_and_evidence(statistics)
        assert confidence == "medium"
        assert evidence == "4 trong 12 lần có yếu tố Giấc ngủ"

    def test_model_authored_number_is_rejected(self):
        output = AgentMoodOutput(
            acknowledgement="Mình đang lắng nghe bạn.",
            observation="Tâm trạng thấp hơn 2 điểm.",
        )
        with pytest.raises(ValueError, match="numbers"):
            _validate_agent_text(output)

    def test_causal_or_markup_model_output_is_rejected(self):
        causal = AgentMoodOutput(
            acknowledgement="Mình đang lắng nghe bạn.",
            observation="Thiếu ngủ chắc chắn gây ra tâm trạng này.",
        )
        with pytest.raises(ValueError, match="causal"):
            _validate_agent_text(causal)

        markup = AgentMoodOutput(
            acknowledgement="Mình đang lắng nghe bạn.",
            observation="**Bạn nên nghỉ ngơi.**",
        )
        with pytest.raises(ValueError, match="Markup"):
            _validate_agent_text(markup)

    def test_external_action_url_is_rejected(self):
        with pytest.raises(ValidationError):
            MoodNextAction(
                type="exercise",
                title="Bài tập",
                url="https://example.com/exercise",
            )

    def test_deleted_exercise_is_not_returned(self):
        entry = self._entry()
        with patch("app.services.mood_analysis.get_exercise", return_value=None):
            assert _safe_action(entry, CrisisLevel.NONE) is None

    def test_crisis_signal_never_returns_regular_exercise(self):
        action = _safe_action(self._entry(), CrisisLevel.LEVEL_3_CRISIS)
        assert action is not None
        assert action.type == "chat"
        assert action.url == "/services/chat"

    async def test_generation_retries_only_once(self):
        entry = self._entry()
        generator = AsyncMock(side_effect=TimeoutError)
        with patch("app.services.mood_analysis._generate_agent_output", generator):
            with pytest.raises(TimeoutError):
                await _generate_with_retry(entry, {"factor_correlations": []})
        assert generator.await_count == 2

    async def test_old_entry_version_cannot_be_published(self):
        old_version = datetime(2026, 7, 21, 1, tzinfo=timezone.utc)
        new_version = datetime(2026, 7, 21, 2, tzinfo=timezone.utc)
        analysis = MagicMock(id=5, user_id=3, entry_updated_at=old_version)
        entry = self._entry(updated_at=new_version)

        latest_result = MagicMock()
        latest_result.scalar_one_or_none.return_value = 5
        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = new_version
        db = AsyncMock()
        db.execute.side_effect = [latest_result, version_result]

        assert await _is_current_job(db, analysis, entry) is False

    async def test_non_latest_job_cannot_be_published(self):
        version = datetime(2026, 7, 21, 2, tzinfo=timezone.utc)
        analysis = MagicMock(id=5, user_id=3, entry_updated_at=version)
        entry = self._entry(updated_at=version)

        latest_result = MagicMock()
        latest_result.scalar_one_or_none.return_value = 6
        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = version
        db = AsyncMock()
        db.execute.side_effect = [latest_result, version_result]

        assert await _is_current_job(db, analysis, entry) is False

    async def test_latest_matching_version_can_be_published(self):
        version = datetime(2026, 7, 21, 2, tzinfo=timezone.utc)
        analysis = MagicMock(id=5, user_id=3, entry_updated_at=version)
        entry = self._entry(updated_at=version)

        latest_result = MagicMock()
        latest_result.scalar_one_or_none.return_value = 5
        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = version
        db = AsyncMock()
        db.execute.side_effect = [latest_result, version_result]

        assert await _is_current_job(db, analysis, entry) is True


class TestMoodAgenticAPI:
    async def test_post_returns_before_worker_and_get_reports_processing(
        self, client: AsyncClient
    ):
        token = await _register_and_login(client, f"mood-processing@{TEST_EMAIL_DOMAIN}")
        with patch("app.api.v1.endpoints.mood.schedule_analysis") as schedule:
            post_response = await client.post(
                "/api/v1/mood/entries",
                headers=_auth(token),
                json={"date": _TODAY, "mood": 3, "energy": "low", "factors": []},
            )
        assert post_response.status_code == 201
        schedule.assert_called_once()

        response = await client.get("/api/v1/mood/insights", headers=_auth(token))
        body = response.json()
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
        assert body["status"] == "processing"
        assert body["analysis_for_entry_id"] == str(post_response.json()["id"])
        assert body["insights"] == []

    async def test_first_checkin_can_receive_safe_acknowledgement(self, client: AsyncClient):
        token = await _register_and_login(client, f"mood-first@{TEST_EMAIL_DOMAIN}")
        with patch("app.api.v1.endpoints.mood.schedule_analysis"):
            post_response = await client.post(
                "/api/v1/mood/entries",
                headers=_auth(token),
                json={"date": _TODAY, "mood": 2, "energy": "low", "factors": []},
            )
        analysis_id = await _analysis_id_for_entry(post_response.json()["id"])
        output = AgentMoodOutput(
            acknowledgement="Có vẻ hôm nay bạn đang có ít năng lượng.",
            observation="Bạn có thể cho mình một khoảng nghỉ thật nhẹ lúc này.",
            follow_up_prompt="Giúp tôi nhìn kỹ hơn tâm trạng hôm nay.",
        )
        with patch(
            "app.services.mood_analysis._generate_agent_output",
            new=AsyncMock(return_value=output),
        ):
            await process_analysis(analysis_id)

        response = await client.get("/api/v1/mood/insights", headers=_auth(token))
        body = response.json()
        assert body["status"] == "ready"
        assert body["generated_by"] == "agent"
        assert body["has_enough_data"] is False
        assert body["reflection"]["acknowledgement"] == output.acknowledgement
        assert body["reflection"]["confidence"] == "low"
        assert body["reflection"]["evidence"] is None

    async def test_model_timeout_publishes_unavailable_rules_fallback(
        self, client: AsyncClient
    ):
        token = await _register_and_login(client, f"mood-timeout@{TEST_EMAIL_DOMAIN}")
        with patch("app.api.v1.endpoints.mood.schedule_analysis"):
            post_response = await client.post(
                "/api/v1/mood/entries",
                headers=_auth(token),
                json={"date": _TODAY, "mood": 3, "energy": "medium", "factors": []},
            )
        analysis_id = await _analysis_id_for_entry(post_response.json()["id"])
        with patch(
            "app.services.mood_analysis._generate_agent_output",
            new=AsyncMock(side_effect=TimeoutError),
        ):
            await process_analysis(analysis_id)

        body = (await client.get("/api/v1/mood/insights", headers=_auth(token))).json()
        assert body["status"] == "unavailable"
        assert body["generated_by"] == "rules"
        assert body["reflection"] is None
        assert body["insights"] == []

    async def test_crisis_note_routes_to_chat_without_calling_model(self, client: AsyncClient):
        token = await _register_and_login(client, f"mood-crisis@{TEST_EMAIL_DOMAIN}")
        with patch("app.api.v1.endpoints.mood.schedule_analysis"):
            post_response = await client.post(
                "/api/v1/mood/entries",
                headers=_auth(token),
                json={
                    "date": _TODAY,
                    "mood": 1,
                    "energy": "low",
                    "factors": [],
                    "note": "Tôi muốn tự tử",
                },
            )
        analysis_id = await _analysis_id_for_entry(post_response.json()["id"])
        with patch(
            "app.services.mood_analysis._generate_agent_output",
            new_callable=AsyncMock,
        ) as generator:
            await process_analysis(analysis_id)

        body = (await client.get("/api/v1/mood/insights", headers=_auth(token))).json()
        generator.assert_not_awaited()
        assert body["status"] == "ready"
        assert body["generated_by"] == "rules"
        assert body["next_action"]["type"] == "chat"
        assert body["next_action"]["url"] == "/services/chat"
