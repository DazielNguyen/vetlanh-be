"""
Unit tests for the personalized recommendation selection service (Phase 1).

Covers:
  - insufficient data → None
  - eligibility via mood entries alone, via PHQ-9 alone
  - each signal branch on its own: PHQ-9 Moderate, PHQ-9 Severe, PHQ-9 Mild,
    mood-trend decline, fallback (most recent mood entry)
  - PHQ-9 Moderate/Severe 30-day recency boundary (29/30 days fires, 31 days
    falls through)
  - precedence ordering at every adjacent boundary in the 4-level chain
  - Moderate/Severe branch only ever returns a calming-allow-list slug
  - rationale templates never contain a score/severity/clinical term
  - Moderate/Severe never falls through to a lower (possibly energizing) branch
    if the calming allow-list can't resolve an exercise
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import recommendation as recommendation_module
from app.services.recommendation import (
    _CALMING_ALLOW_LIST,
    _RATIONALE,
    get_personalized_recommendation,
)

_FIXED_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_TODAY = date(2026, 6, 15)


def _make_mood_entry(*, date_val: date, mood: int, user_id: int = 1) -> MagicMock:
    m = MagicMock()
    m.date = date_val
    m.mood = mood
    m.user_id = user_id
    return m


def _make_assessment(*, severity: str, days_ago: int, user_id: int = 1) -> MagicMock:
    m = MagicMock()
    m.severity = severity
    m.user_id = user_id
    m.created_at = _FIXED_NOW - timedelta(days=days_ago)
    return m


def _make_db(mood_entries: list, assessment) -> AsyncMock:
    """First db.execute() call returns the mood-entry list, second returns the
    latest assessment scalar — matching call order in get_personalized_recommendation."""
    mood_result = MagicMock()
    mood_result.scalars.return_value.all.return_value = mood_entries

    assessment_result = MagicMock()
    assessment_result.scalar_one_or_none.return_value = assessment

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[mood_result, assessment_result])
    return db


def _flat_entries(mood: int = 3, days: int = 3) -> list:
    """Recent entries with no prior-week data, so trend never fires."""
    return [_make_mood_entry(date_val=_TODAY - timedelta(days=i), mood=mood) for i in range(days)]


def _declining_entries() -> list:
    """Prior week mood=5 every day, current week mood=2 every day → clear decline."""
    current = [_make_mood_entry(date_val=_TODAY - timedelta(days=i), mood=2) for i in range(7)]
    prior = [_make_mood_entry(date_val=_TODAY - timedelta(days=7 + i), mood=5) for i in range(7)]
    return current + prior


async def _run(mood_entries, assessment):
    db = _make_db(mood_entries, assessment)
    with patch("app.services.recommendation.datetime") as mock_dt:
        mock_dt.now.return_value = _FIXED_NOW
        return await get_personalized_recommendation(db, user_id=1)


class TestEligibility:
    async def test_no_entries_no_assessment_returns_none(self):
        result = await _run([], None)
        assert result is None

    async def test_two_recent_entries_below_threshold_no_assessment_returns_none(self):
        result = await _run(_flat_entries(days=2), None)
        assert result is None

    async def test_three_recent_entries_eligible(self):
        result = await _run(_flat_entries(days=3), None)
        assert result is not None

    async def test_assessment_alone_with_no_entries_eligible(self):
        # Minimal severity fires no signal branch, but "eligible" (has a PHQ-9 ever)
        # is still true — it just means every branch is checked, not that one must fire.
        result = await _run([], _make_assessment(severity="Mild", days_ago=0))
        assert result is not None

    async def test_eligible_via_assessment_but_no_branch_fires_returns_none(self):
        # Minimal severity + no mood entries: eligible, but no branch matches -> None.
        result = await _run([], _make_assessment(severity="Minimal", days_ago=0))
        assert result is None


class TestSignalBranches:
    async def test_moderate_phq9_fires_calming_branch(self):
        result = await _run([], _make_assessment(severity="Moderate", days_ago=0))
        assert result.rationale == _RATIONALE["phq9_high"]

    async def test_severe_phq9_fires_calming_branch(self):
        result = await _run([], _make_assessment(severity="Severe", days_ago=0))
        assert result.rationale == _RATIONALE["phq9_high"]

    async def test_mood_trend_decline_fires_trend_branch(self):
        result = await _run(_declining_entries(), None)
        assert result.rationale == _RATIONALE["trend_decline"]

    async def test_mild_phq9_fires_mild_branch(self):
        result = await _run([], _make_assessment(severity="Mild", days_ago=0))
        assert result.rationale == _RATIONALE["phq9_mild"]

    async def test_flat_entries_no_assessment_fires_fallback_branch(self):
        result = await _run(_flat_entries(days=3), None)
        assert result.rationale == _RATIONALE["fallback"]


class TestPhq9RecencyBoundary:
    async def test_moderate_at_29_days_still_fires(self):
        result = await _run([], _make_assessment(severity="Moderate", days_ago=29))
        assert result.rationale == _RATIONALE["phq9_high"]

    async def test_moderate_at_30_days_still_fires(self):
        result = await _run([], _make_assessment(severity="Moderate", days_ago=30))
        assert result.rationale == _RATIONALE["phq9_high"]

    async def test_moderate_at_31_days_falls_through_to_none(self):
        # No mood entries, no other signal available -> stale Moderate result must not
        # lock the user into calming content indefinitely.
        result = await _run([], _make_assessment(severity="Moderate", days_ago=31))
        assert result is None


class TestPrecedenceBoundaries:
    async def test_moderate_beats_simultaneous_trend_decline(self):
        result = await _run(_declining_entries(), _make_assessment(severity="Moderate", days_ago=0))
        assert result.rationale == _RATIONALE["phq9_high"]

    async def test_trend_decline_beats_simultaneous_mild(self):
        result = await _run(_declining_entries(), _make_assessment(severity="Mild", days_ago=0))
        assert result.rationale == _RATIONALE["trend_decline"]

    async def test_mild_beats_simultaneous_fallback_only_signal(self):
        # Flat entries alone would only satisfy the fallback branch; Mild must win.
        result = await _run(_flat_entries(days=3), _make_assessment(severity="Mild", days_ago=0))
        assert result.rationale == _RATIONALE["phq9_mild"]


class TestClinicalSafety:
    async def test_moderate_branch_only_returns_allow_listed_slug(self):
        result = await _run([], _make_assessment(severity="Moderate", days_ago=0))
        assert result.url in {f"/services/exercises/{slug}" for slug in _CALMING_ALLOW_LIST}

    async def test_severe_branch_only_returns_allow_listed_slug(self):
        result = await _run([], _make_assessment(severity="Severe", days_ago=0))
        assert result.url in {f"/services/exercises/{slug}" for slug in _CALMING_ALLOW_LIST}

    async def test_moderate_never_falls_through_to_energizing_branch(self):
        # If the calming allow-list can't resolve an exercise (e.g. catalog drift),
        # the branch must return None outright -- never fall through to a lower
        # branch that could pick an energizing exercise for a distressed user.
        entries = _declining_entries()  # would otherwise fire the trend branch
        with patch.object(recommendation_module, "get_exercise", return_value=None):
            result = await _run(entries, _make_assessment(severity="Moderate", days_ago=0))
        assert result is None

    def test_no_rationale_contains_score_or_clinical_terms(self):
        forbidden = ("phq", "moderate", "severe", "mild", "minimal", "depress", "chẩn đoán")
        for text in _RATIONALE.values():
            assert not any(char.isdigit() for char in text)
            lowered = text.lower()
            assert not any(term in lowered for term in forbidden)


class TestUrlShape:
    async def test_every_returned_url_starts_with_single_slash(self):
        cases = [
            ([], _make_assessment(severity="Severe", days_ago=0)),
            (_declining_entries(), None),
            ([], _make_assessment(severity="Mild", days_ago=0)),
            (_flat_entries(days=3), None),
        ]
        for mood_entries, assessment in cases:
            result = await _run(mood_entries, assessment)
            assert result is not None
            assert result.url.startswith("/") and not result.url.startswith("//")
