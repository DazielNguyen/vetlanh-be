import unittest.mock as mock
from uuid import uuid4

from httpx import AsyncClient


async def _register_and_login(client: AsyncClient) -> str:
    captured = []
    email = f"reflections-{uuid4().hex}@test.vetlanh"

    async def capture(*args, **kwargs):
        captured.append(args)

    with mock.patch(
        "app.api.v1.endpoints.auth.send_verification_email",
        side_effect=capture,
    ):
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass1"},
        )
    assert response.status_code == 201

    await client.get(f"/api/v1/auth/verify?token={captured[0][1]}")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "securepass1"},
    )
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_journal(client: AsyncClient, token: str, **overrides) -> dict:
    payload = {"title": "Nhật ký", "content": "Một ngày bình thường"}
    payload.update(overrides)
    response = await client.post("/api/v1/journal", json=payload, headers=_auth(token))
    assert response.status_code == 201
    return response.json()


async def _create_thought(client: AsyncClient, token: str, **overrides) -> dict:
    payload = {
        "situation": "Cuộc họp sáng nay",
        "automatic_thought": "Mọi người không hài lòng với mình",
        "emotion": "Lo lắng 70%",
        "evidence": "Sếp hỏi lại hai lần",
    }
    payload.update(overrides)
    response = await client.post(
        "/api/v1/thought-records", json=payload, headers=_auth(token)
    )
    assert response.status_code == 201
    return response.json()


async def test_reflections_requires_authentication(client: AsyncClient):
    response = await client.get("/api/v1/reflections")

    assert response.status_code == 401


async def test_empty_reflection_feed(client: AsyncClient):
    token = await _register_and_login(client)

    response = await client.get("/api/v1/reflections", headers=_auth(token))

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


async def test_mixed_feed_mapping_type_search_and_global_order(client: AsyncClient):
    token = await _register_and_login(client)
    journal = await _create_journal(
        client,
        token,
        title=None,
        content="<p>Mình thấy Bí Mật &amp; nhẹ hơn</p>",
    )
    thought = await _create_thought(client, token, evidence="Bằng chứng bí mật")

    response = await client.get(
        "/api/v1/reflections?q=%20b%C3%AD%20m%E1%BA%ADt%20",
        headers=_auth(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [
        f"thought_record:{thought['id']}",
        f"journal:{journal['id']}",
    ]
    assert body["items"][1]["title"] == "Một ghi chép nhỏ"
    assert body["items"][1]["preview"] == "Mình thấy Bí Mật & nhẹ hơn"
    assert "emotion" not in body["items"][1]

    journals_only = await client.get(
        "/api/v1/reflections?type=journal&q=b%C3%AD%20m%E1%BA%ADt",
        headers=_auth(token),
    )
    assert [item["type"] for item in journals_only.json()["items"]] == ["journal"]


async def test_cursor_pagination_has_no_duplicates(client: AsyncClient):
    token = await _register_and_login(client)
    await _create_journal(client, token, title="Một")
    await _create_thought(client, token, situation="Hai")
    await _create_journal(client, token, title="Ba")

    first = await client.get("/api/v1/reflections?limit=2", headers=_auth(token))
    assert first.status_code == 200
    cursor = first.json()["next_cursor"]
    assert cursor

    second = await client.get(
        "/api/v1/reflections",
        params={"limit": 2, "cursor": cursor},
        headers=_auth(token),
    )
    first_ids = {item["id"] for item in first.json()["items"]}
    second_ids = {item["id"] for item in second.json()["items"]}
    assert first_ids.isdisjoint(second_ids)
    assert len(first_ids | second_ids) == 3


async def test_reflections_are_isolated_by_authenticated_user(client: AsyncClient):
    first_token = await _register_and_login(client)
    second_token = await _register_and_login(client)
    own = await _create_journal(client, first_token, title="Của tôi")
    await _create_journal(client, second_token, title="Không được thấy")

    response = await client.get("/api/v1/reflections", headers=_auth(first_token))

    assert [item["resource_id"] for item in response.json()["items"]] == [
        str(own["id"])
    ]


async def test_validation_rejects_bad_filters_and_cursor(client: AsyncClient):
    token = await _register_and_login(client)

    for query in ("type=unknown", "limit=0", "limit=51", "cursor=broken"):
        response = await client.get(
            f"/api/v1/reflections?{query}", headers=_auth(token)
        )
        assert response.status_code == 422, query


async def test_feed_reflects_underlying_update_and_delete(client: AsyncClient):
    token = await _register_and_login(client)
    journal = await _create_journal(client, token, title="Cũ")

    update = await client.patch(
        f"/api/v1/journal/{journal['id']}",
        json={"title": "Mới"},
        headers=_auth(token),
    )
    assert update.status_code == 200
    feed = await client.get("/api/v1/reflections", headers=_auth(token))
    assert feed.json()["items"][0]["title"] == "Mới"

    delete = await client.delete(
        f"/api/v1/journal/{journal['id']}", headers=_auth(token)
    )
    assert delete.status_code == 204
    feed = await client.get("/api/v1/reflections", headers=_auth(token))
    assert feed.json()["items"] == []
