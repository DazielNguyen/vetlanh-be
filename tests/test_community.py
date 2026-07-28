import asyncio
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy import select, text

from app.core import deps
from app.core.database import AsyncSessionLocal
from app.models.community import CommunityReport


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _user(client: AsyncClient, name: str) -> tuple[str, str]:
    email = f"community-{name}@test.vetlanh"
    payload = {"email": email, "password": "securepass1"}
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    response = await client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    return email, response.json()["access_token"]


async def _matched_pair(
    client: AsyncClient, suffix: str
) -> tuple[str, str, str]:
    _, token1 = await _user(client, f"{suffix}-one")
    _, token2 = await _user(client, f"{suffix}-two")
    waiting = await client.post("/api/v1/community/opt-in", headers=_auth(token1))
    assert waiting.json() == {"status": "waiting", "match": None}
    matched = await client.post("/api/v1/community/opt-in", headers=_auth(token2))
    assert matched.status_code == 200
    return token1, token2, matched.json()["match"]["matchId"]


class TestCommunityMatching:
    async def test_status_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/community/match/status")
        assert response.status_code in (401, 403)

    async def test_opt_in_is_idempotent_and_matches_anonymously(
        self, client: AsyncClient
    ):
        _, token1 = await _user(client, "matching-one")
        _, token2 = await _user(client, "matching-two")

        first = await client.post(
            "/api/v1/community/opt-in", headers=_auth(token1)
        )
        repeated = await client.post(
            "/api/v1/community/opt-in", headers=_auth(token1)
        )
        assert first.json() == repeated.json() == {
            "status": "waiting",
            "match": None,
        }

        second = await client.post(
            "/api/v1/community/opt-in", headers=_auth(token2)
        )
        status1 = await client.get(
            "/api/v1/community/match/status", headers=_auth(token1)
        )
        for body in (second.json(), status1.json()):
            assert body["status"] == "matched"
            assert body["match"]["matchId"].startswith("m_")
            assert body["match"]["partnerHandle"].startswith(
                "Người bạn ẩn danh #"
            )
            serialized = str(body).lower()
            assert "email" not in serialized
            assert "avatar" not in serialized
            assert "user_id" not in serialized

    async def test_concurrent_opt_in_does_not_create_multiple_matches(
        self, client: AsyncClient
    ):
        tokens = [(await _user(client, f"race-{i}"))[1] for i in range(4)]
        responses = await asyncio.gather(
            *[
                client.post("/api/v1/community/opt-in", headers=_auth(token))
                for token in tokens
            ]
        )
        assert all(response.status_code == 200 for response in responses)
        async with AsyncSessionLocal() as db:
            active = (
                await db.execute(
                    text(
                        "SELECT COUNT(*) FROM community_matches "
                        "WHERE status = 'active'"
                    )
                )
            ).scalar_one()
            duplicate = (
                await db.execute(
                    text(
                        "SELECT active_match_id, COUNT(*) "
                        "FROM community_participations "
                        "WHERE active_match_id IS NOT NULL "
                        "GROUP BY active_match_id HAVING COUNT(*) <> 2"
                    )
                )
            ).all()
        assert active == 2
        assert duplicate == []

    async def test_opt_out_is_idempotent(self, client: AsyncClient):
        _, token = await _user(client, "opt-out")
        for _ in range(2):
            response = await client.post(
                "/api/v1/community/opt-out", headers=_auth(token)
            )
            assert response.status_code == 204
        status = await client.get(
            "/api/v1/community/match/status", headers=_auth(token)
        )
        assert status.json()["status"] == "opted_out"


class TestCommunityMessages:
    async def test_message_ownership_and_history(self, client: AsyncClient):
        token1, token2, match_id = await _matched_pair(client, "messages")
        sent = await client.post(
            f"/api/v1/community/match/{match_id}/messages",
            json={"content": "<script>alert('x')</script>"},
            headers=_auth(token1),
        )
        assert sent.status_code == 201
        assert sent.json()["isMine"] is True
        assert sent.json()["content"] == "<script>alert('x')</script>"

        history = await client.get(
            f"/api/v1/community/match/{match_id}/messages",
            headers=_auth(token2),
        )
        assert history.status_code == 200
        assert history.json()[0]["isMine"] is False

    async def test_outsider_cannot_access_messages(self, client: AsyncClient):
        _, _, match_id = await _matched_pair(client, "outsider")
        _, outsider = await _user(client, "outsider-third")
        for method in ("get", "post"):
            kwargs = (
                {"json": {"content": "no access"}}
                if method == "post"
                else {}
            )
            response = await getattr(client, method)(
                f"/api/v1/community/match/{match_id}/messages",
                headers=_auth(outsider),
                **kwargs,
            )
            assert response.status_code == 403

    async def test_blank_and_too_long_messages_are_rejected(
        self, client: AsyncClient
    ):
        token1, _, match_id = await _matched_pair(client, "length")
        for content in ("   ", "x" * 2001):
            response = await client.post(
                f"/api/v1/community/match/{match_id}/messages",
                json={"content": content},
                headers=_auth(token1),
            )
            assert response.status_code == 422

    async def test_message_push_is_targeted_to_partner(
        self, client: AsyncClient
    ):
        token1, _, match_id = await _matched_pair(client, "push")
        with patch(
            "app.api.v1.endpoints.community.send_to_user",
            new_callable=AsyncMock,
        ) as push:
            response = await client.post(
                f"/api/v1/community/match/{match_id}/messages",
                json={"content": "Xin chào"},
                headers=_auth(token1),
            )
        assert response.status_code == 201
        push.assert_awaited_once()
        _, event_name, arguments = push.await_args.args
        assert event_name == "ReceiveCommunityMessage"
        assert arguments[0]["isMine"] is False
        assert "userId" not in arguments[0]
        assert "email" not in arguments[0]


class TestCommunitySafety:
    async def test_exit_is_idempotent(self, client: AsyncClient):
        token1, _, match_id = await _matched_pair(client, "exit")
        for _ in range(2):
            response = await client.post(
                f"/api/v1/community/match/{match_id}/exit",
                headers=_auth(token1),
            )
            assert response.status_code == 204

    async def test_blocked_pair_is_not_immediately_rematched(
        self, client: AsyncClient
    ):
        token1, token2, match_id = await _matched_pair(client, "block")
        response = await client.post(
            f"/api/v1/community/match/{match_id}/block",
            headers=_auth(token1),
        )
        assert response.status_code == 204
        await client.post("/api/v1/community/opt-in", headers=_auth(token1))
        await client.post("/api/v1/community/opt-in", headers=_auth(token2))
        statuses = [
            (
                await client.get(
                    "/api/v1/community/match/status", headers=_auth(token)
                )
            ).json()["status"]
            for token in (token1, token2)
        ]
        assert statuses == ["waiting", "waiting"]

    async def test_report_is_idempotent_and_has_eight_hour_sla(
        self, client: AsyncClient
    ):
        token1, _, match_id = await _matched_pair(client, "report")
        for _ in range(2):
            response = await client.post(
                f"/api/v1/community/match/{match_id}/report",
                json={"reason": "Ngôn từ khó chịu"},
                headers=_auth(token1),
            )
            assert response.status_code == 204
        async with AsyncSessionLocal() as db:
            reports = (
                await db.execute(select(CommunityReport))
            ).scalars().all()
        assert len(reports) == 1
        assert (
            reports[0].sla_deadline - reports[0].reported_at
        ).total_seconds() == 8 * 60 * 60


class TestCommunityAdmin:
    async def test_admin_can_list_warn_and_ban(
        self, client: AsyncClient, monkeypatch
    ):
        _, admin_token = await _user(client, "admin")
        monkeypatch.setattr(
            deps, "_ADMIN_USERS", frozenset({"community-admin@test.vetlanh"})
        )
        reporter, reported, match_id = await _matched_pair(client, "admin-report")
        await client.post(
            f"/api/v1/community/match/{match_id}/report",
            json={},
            headers=_auth(reporter),
        )

        queue = await client.get(
            "/api/v1/admin/community/reports",
            headers=_auth(admin_token),
        )
        assert queue.status_code == 200
        report_id = queue.json()[0]["id"]
        warned = await client.post(
            f"/api/v1/admin/community/reports/{report_id}/warn",
            headers=_auth(admin_token),
        )
        assert warned.status_code == 200
        assert warned.json()["status"] == "resolved"
        repeated = await client.post(
            f"/api/v1/admin/community/reports/{report_id}/warn",
            headers=_auth(admin_token),
        )
        assert repeated.status_code == 404

        # Create a fresh report to verify a ban prevents future opt-in.
        await client.post(
            "/api/v1/community/opt-out", headers=_auth(reported)
        )
        reporter2, reported2, match2 = await _matched_pair(client, "admin-ban")
        await client.post(
            f"/api/v1/community/match/{match2}/report",
            json={},
            headers=_auth(reporter2),
        )
        queue = await client.get(
            "/api/v1/admin/community/reports",
            headers=_auth(admin_token),
        )
        open_report = queue.json()[0]
        banned = await client.post(
            f"/api/v1/admin/community/reports/{open_report['id']}/ban",
            headers=_auth(admin_token),
        )
        assert banned.status_code == 200
        rejected = await client.post(
            "/api/v1/community/opt-in", headers=_auth(reported2)
        )
        assert rejected.status_code == 403

    async def test_non_admin_is_rejected(self, client: AsyncClient):
        _, token = await _user(client, "not-admin")
        response = await client.get(
            "/api/v1/admin/community/reports", headers=_auth(token)
        )
        assert response.status_code == 403


class TestCommunityFeatured:
    async def test_count_comes_from_real_participation_rows(
        self, client: AsyncClient
    ):
        initial = await client.get("/api/v1/community/featured")
        assert initial.status_code == 200
        assert initial.json()["active_users_count"] == 0
        _, token = await _user(client, "featured")
        await client.post("/api/v1/community/opt-in", headers=_auth(token))
        updated = await client.get("/api/v1/community/featured")
        assert updated.json()["active_users_count"] == 1
