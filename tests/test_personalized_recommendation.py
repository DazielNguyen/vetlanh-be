"""
Integration tests for GET /api/v1/dashboard/personalized-recommendation (Phase 2).

Covers:
  Auth:
    - 401 without token
    - 401 with invalid token
  Behavior:
    - fresh user with no history -> 200, null body
    - PHQ-9 Moderate/Severe -> 200, calming exercise from the curated allow-list
    - mood-trend decline (no PHQ-9) -> 200, well-formed recommendation
    - every non-null url matches the exact /services/exercises/{slug} FE-route prefix
    - existing /dashboard and /exercises/recommended endpoints unaffected (spot check)
"""

from datetime import date, timedelta

from httpx import AsyncClient

from app.services.recommendation import _CALMING_ALLOW_LIST

TEST_EMAIL_DOMAIN = "test.vetlanh"

_URL_PREFIX = "/services/exercises/"

# PHQ-9 answer sets summing into known severity bands (severity thresholds:
# Minimal 0-4, Mild 5-9, Moderate 10-14, Severe 15+).
_SEVERE_ANSWERS = [3, 3, 3, 2, 2, 1, 1, 0, 0]  # sum = 15
_MODERATE_ANSWERS = [2, 2, 2, 2, 1, 1, 1, 1, 0]  # sum = 12


async def _register_and_login(client: AsyncClient, email: str) -> str:
    creds = {"email": email, "password": "securepass1"}
    resp = await client.post("/api/v1/auth/register", json=creds)
    assert resp.status_code == 201, f"Register failed: {resp.text}"
    resp = await client.post("/api/v1/auth/login", json=creds)
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _submit_phq9(client: AsyncClient, headers: dict, answers: list[int]) -> None:
    resp = await client.post(
        "/api/v1/assessments/phq9", json={"answers": answers}, headers=headers
    )
    assert resp.status_code == 201, f"PHQ-9 submit failed: {resp.text}"


async def _checkin(client: AsyncClient, headers: dict, day: date, mood: int) -> None:
    resp = await client.post(
        "/api/v1/mood/entries",
        json={"mood": mood, "date": day.isoformat()},
        headers=headers,
    )
    assert resp.status_code == 201, f"Mood check-in failed: {resp.text}"


async def _seed_declining_trend(client: AsyncClient, headers: dict) -> None:
    today = date.today()
    for i in range(7):
        await _checkin(client, headers, today - timedelta(days=i), mood=2)
    for i in range(7):
        await _checkin(client, headers, today - timedelta(days=7 + i), mood=5)


class TestPersonalizedRecommendationAuth:
    async def test_without_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/dashboard/personalized-recommendation")
        assert resp.status_code == 401

    async def test_invalid_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/dashboard/personalized-recommendation",
            headers=_auth("not-a-real-token"),
        )
        assert resp.status_code == 401


class TestPersonalizedRecommendationBehavior:
    async def test_fresh_user_gets_null_body(self, client: AsyncClient):
        token = await _register_and_login(client, "reco_fresh@test.vetlanh")
        resp = await client.get(
            "/api/v1/dashboard/personalized-recommendation", headers=_auth(token)
        )
        assert resp.status_code == 200
        assert resp.json() is None

    async def test_severe_phq9_returns_calming_exercise(self, client: AsyncClient):
        token = await _register_and_login(client, "reco_severe@test.vetlanh")
        headers = _auth(token)
        await _submit_phq9(client, headers, _SEVERE_ANSWERS)

        resp = await client.get(
            "/api/v1/dashboard/personalized-recommendation", headers=headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body is not None
        assert set(body.keys()) == {"title", "rationale", "url"}
        assert body["url"].startswith(_URL_PREFIX)
        slug = body["url"][len(_URL_PREFIX):]
        assert slug in _CALMING_ALLOW_LIST

    async def test_moderate_phq9_returns_calming_exercise(self, client: AsyncClient):
        token = await _register_and_login(client, "reco_moderate@test.vetlanh")
        headers = _auth(token)
        await _submit_phq9(client, headers, _MODERATE_ANSWERS)

        resp = await client.get(
            "/api/v1/dashboard/personalized-recommendation", headers=headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body is not None
        slug = body["url"][len(_URL_PREFIX):]
        assert slug in _CALMING_ALLOW_LIST

    async def test_mood_trend_decline_returns_recommendation(self, client: AsyncClient):
        token = await _register_and_login(client, "reco_trend@test.vetlanh")
        headers = _auth(token)
        await _seed_declining_trend(client, headers)

        resp = await client.get(
            "/api/v1/dashboard/personalized-recommendation", headers=headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body is not None
        assert body["url"].startswith(_URL_PREFIX)
        assert body["title"]
        assert body["rationale"]

    async def test_response_shape_matches_spec_exactly(self, client: AsyncClient):
        token = await _register_and_login(client, "reco_shape@test.vetlanh")
        headers = _auth(token)
        await _submit_phq9(client, headers, _SEVERE_ANSWERS)

        resp = await client.get(
            "/api/v1/dashboard/personalized-recommendation", headers=headers
        )
        body = resp.json()
        assert isinstance(body["title"], str) and body["title"]
        assert isinstance(body["rationale"], str) and body["rationale"]
        assert isinstance(body["url"], str) and body["url"].startswith("/") and not body["url"].startswith("//")


class TestExistingEndpointsUnaffected:
    async def test_dashboard_endpoint_still_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "reco_regress_dash@test.vetlanh")
        resp = await client.get("/api/v1/dashboard", headers=_auth(token))
        assert resp.status_code == 200

    async def test_recommended_exercises_endpoint_still_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "reco_regress_ex@test.vetlanh")
        resp = await client.get(
            "/api/v1/exercises/recommended", params={"mood": "anxious"}, headers=_auth(token)
        )
        assert resp.status_code == 200
