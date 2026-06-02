"""
Tests for Crisis Detection feature — US-022 / US-023.

Covers:
  Service unit tests (detect_crisis_level):
    - unrelated text → NONE (0)
    - level-1 anxiety keywords → LEVEL_1_ANXIETY (1)
    - level-2 serious keywords → LEVEL_2_SERIOUS (2)
    - level-3 crisis keywords  → LEVEL_3_CRISIS (3)
    - higher level takes priority when multiple levels present
    - matching is case-insensitive
    - keyword embedded in longer sentence still matches
    - empty string → NONE
    - whitespace-only → NONE

  API integration tests (GET /api/v1/crisis/resources):
    - returns 200 without authentication
    - returns 200 even with invalid bearer token
    - response has hotlines list
    - response hotlines list is non-empty
    - each hotline has name, number, description, available fields
    - response has breathing_exercise dict
    - breathing_exercise has exercise_slug, title, description fields
    - response has message field
    - breathing_exercise slug references a real exercise
"""

import pytest
from httpx import AsyncClient

from app.services.crisis import CrisisLevel, detect_crisis_level


# ===========================================================================
# SERVICE UNIT TESTS
# ===========================================================================


class TestDetectCrisisLevelNone:
    """Texts with no crisis keywords → NONE."""

    def test_empty_string_returns_none(self):
        assert detect_crisis_level("") == CrisisLevel.NONE

    def test_whitespace_only_returns_none(self):
        assert detect_crisis_level("   ") == CrisisLevel.NONE

    def test_unrelated_text_returns_none(self):
        assert detect_crisis_level("Hôm nay thời tiết đẹp quá!") == CrisisLevel.NONE

    def test_greeting_returns_none(self):
        assert detect_crisis_level("Xin chào, bạn có khỏe không?") == CrisisLevel.NONE

    def test_positive_sentiment_returns_none(self):
        assert detect_crisis_level("Tôi cảm thấy vui vẻ và hạnh phúc hôm nay.") == CrisisLevel.NONE

    def test_random_numbers_return_none(self):
        assert detect_crisis_level("12345 67890") == CrisisLevel.NONE

    def test_english_unrelated_text_returns_none(self):
        assert detect_crisis_level("Hello world, how are you?") == CrisisLevel.NONE


class TestDetectCrisisLevelOne:
    """Level-1 anxiety keywords → LEVEL_1_ANXIETY."""

    def test_kho_tho_returns_level_1(self):
        assert detect_crisis_level("tôi bị khó thở") == CrisisLevel.LEVEL_1_ANXIETY

    def test_hoang_loan_returns_level_1(self):
        assert detect_crisis_level("tôi đang hoảng loạn") == CrisisLevel.LEVEL_1_ANXIETY

    def test_panic_english_returns_level_1(self):
        assert detect_crisis_level("I'm having a panic attack") == CrisisLevel.LEVEL_1_ANXIETY

    def test_lo_au_returns_level_1(self):
        assert detect_crisis_level("lo âu mãi không hết") == CrisisLevel.LEVEL_1_ANXIETY

    def test_hoi_hop_returns_level_1(self):
        assert detect_crisis_level("tim đập nhanh, hồi hộp lắm") == CrisisLevel.LEVEL_1_ANXIETY

    def test_stress_qua_returns_level_1(self):
        assert detect_crisis_level("stress quá không chịu được nữa") == CrisisLevel.LEVEL_1_ANXIETY

    def test_run_so_returns_level_1(self):
        assert detect_crisis_level("tay chân run sợ hết cả") == CrisisLevel.LEVEL_1_ANXIETY

    def test_keyword_in_sentence_returns_level_1(self):
        assert detect_crisis_level("Tôi cảm thấy rất bất an khi nghĩ đến việc đó.") == CrisisLevel.LEVEL_1_ANXIETY


class TestDetectCrisisLevelTwo:
    """Level-2 serious keywords → LEVEL_2_SERIOUS."""

    def test_tuyet_vong_returns_level_2(self):
        assert detect_crisis_level("tôi cảm thấy tuyệt vọng") == CrisisLevel.LEVEL_2_SERIOUS

    def test_be_tac_returns_level_2(self):
        assert detect_crisis_level("cuộc sống bế tắc quá") == CrisisLevel.LEVEL_2_SERIOUS

    def test_muon_bien_mat_returns_level_2(self):
        assert detect_crisis_level("chỉ muốn biến mất thôi") == CrisisLevel.LEVEL_2_SERIOUS

    def test_chan_song_returns_level_2(self):
        assert detect_crisis_level("tôi chán sống lắm rồi") == CrisisLevel.LEVEL_2_SERIOUS

    def test_khong_co_tuong_lai_returns_level_2(self):
        assert detect_crisis_level("tôi không có tương lai") == CrisisLevel.LEVEL_2_SERIOUS

    def test_vo_vong_returns_level_2(self):
        assert detect_crisis_level("cảm giác vô vọng không tả được") == CrisisLevel.LEVEL_2_SERIOUS

    def test_tu_lam_hai_returns_level_2(self):
        assert detect_crisis_level("tôi đang tự làm hại bản thân") == CrisisLevel.LEVEL_2_SERIOUS

    def test_khong_loi_thoat_returns_level_2(self):
        assert detect_crisis_level("không lối thoát nào cả") == CrisisLevel.LEVEL_2_SERIOUS


class TestDetectCrisisLevelThree:
    """Level-3 crisis keywords → LEVEL_3_CRISIS."""

    def test_muon_tu_tu_returns_level_3(self):
        assert detect_crisis_level("muốn tự tử") == CrisisLevel.LEVEL_3_CRISIS

    def test_tu_tu_returns_level_3(self):
        assert detect_crisis_level("tôi đang nghĩ đến tự tử") == CrisisLevel.LEVEL_3_CRISIS

    def test_muon_chet_returns_level_3(self):
        assert detect_crisis_level("tôi muốn chết") == CrisisLevel.LEVEL_3_CRISIS

    def test_cat_tay_returns_level_3(self):
        assert detect_crisis_level("tôi muốn cắt tay") == CrisisLevel.LEVEL_3_CRISIS

    def test_chet_la_het_returns_level_3(self):
        assert detect_crisis_level("chết là hết mọi chuyện thôi") == CrisisLevel.LEVEL_3_CRISIS

    def test_ket_thuc_cuoc_doi_returns_level_3(self):
        assert detect_crisis_level("muốn kết thúc cuộc đời") == CrisisLevel.LEVEL_3_CRISIS

    def test_khong_muon_song_nua_returns_level_3(self):
        assert detect_crisis_level("không muốn sống nữa rồi") == CrisisLevel.LEVEL_3_CRISIS

    def test_nhay_xuong_returns_level_3(self):
        assert detect_crisis_level("đang đứng trên sân thượng muốn nhảy xuống") == CrisisLevel.LEVEL_3_CRISIS


class TestDetectCrisisLevelPriority:
    """Higher levels always take priority when multiple keywords are present."""

    def test_level3_beats_level2_and_level1(self):
        text = "tôi lo âu và tuyệt vọng, muốn tự tử"
        assert detect_crisis_level(text) == CrisisLevel.LEVEL_3_CRISIS

    def test_level2_beats_level1(self):
        text = "tim đập nhanh và tôi cảm thấy bế tắc quá"
        assert detect_crisis_level(text) == CrisisLevel.LEVEL_2_SERIOUS

    def test_level3_beats_level1_only(self):
        text = "khó thở và muốn chết đi cho xong"
        assert detect_crisis_level(text) == CrisisLevel.LEVEL_3_CRISIS

    def test_level3_beats_level2_only(self):
        text = "vô vọng và muốn tự tử"
        assert detect_crisis_level(text) == CrisisLevel.LEVEL_3_CRISIS


class TestDetectCrisisLevelCaseInsensitive:
    """Matching must be case-insensitive."""

    def test_uppercase_level1(self):
        assert detect_crisis_level("KHÓ THỞ") == CrisisLevel.LEVEL_1_ANXIETY

    def test_uppercase_level2(self):
        assert detect_crisis_level("TUYỆT VỌNG") == CrisisLevel.LEVEL_2_SERIOUS

    def test_uppercase_level3(self):
        assert detect_crisis_level("MUỐN TỰ TỬ") == CrisisLevel.LEVEL_3_CRISIS

    def test_mixed_case_panic(self):
        assert detect_crisis_level("Panic Attack") == CrisisLevel.LEVEL_1_ANXIETY

    def test_mixed_case_level3(self):
        assert detect_crisis_level("Muốn Chết đi Cho Xong") == CrisisLevel.LEVEL_3_CRISIS


class TestDetectCrisisLevelReturnType:
    """Return type is always a CrisisLevel IntEnum."""

    def test_none_is_int_zero(self):
        result = detect_crisis_level("hello")
        assert result == 0
        assert isinstance(result, CrisisLevel)

    def test_level3_is_int_three(self):
        result = detect_crisis_level("muốn tự tử")
        assert result == 3
        assert isinstance(result, CrisisLevel)

    def test_level1_is_int_one(self):
        result = detect_crisis_level("khó thở")
        assert result == 1

    def test_level2_is_int_two(self):
        result = detect_crisis_level("tuyệt vọng")
        assert result == 2


# ===========================================================================
# API INTEGRATION TESTS — GET /api/v1/crisis/resources
# ===========================================================================


class TestCrisisResourcesNoAuth:
    """The /crisis/resources endpoint must be accessible without authentication."""

    async def test_returns_200_without_token(self, client: AsyncClient):
        resp = await client.get("/api/v1/crisis/resources")
        assert resp.status_code == 200

    async def test_returns_200_with_invalid_bearer_token(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/crisis/resources",
            headers={"Authorization": "Bearer totally.invalid.token"},
        )
        assert resp.status_code == 200

    async def test_returns_200_with_no_headers(self, client: AsyncClient):
        resp = await client.get("/api/v1/crisis/resources")
        assert resp.status_code == 200


class TestCrisisResourcesResponseShape:
    """Response must contain the correct structure."""

    async def test_response_has_hotlines_key(self, client: AsyncClient):
        resp = await client.get("/api/v1/crisis/resources")
        assert "hotlines" in resp.json()

    async def test_response_has_breathing_exercise_key(self, client: AsyncClient):
        resp = await client.get("/api/v1/crisis/resources")
        assert "breathing_exercise" in resp.json()

    async def test_response_has_message_key(self, client: AsyncClient):
        resp = await client.get("/api/v1/crisis/resources")
        assert "message" in resp.json()

    async def test_hotlines_is_list(self, client: AsyncClient):
        resp = await client.get("/api/v1/crisis/resources")
        assert isinstance(resp.json()["hotlines"], list)

    async def test_hotlines_is_non_empty(self, client: AsyncClient):
        resp = await client.get("/api/v1/crisis/resources")
        assert len(resp.json()["hotlines"]) > 0

    async def test_each_hotline_has_required_fields(self, client: AsyncClient):
        resp = await client.get("/api/v1/crisis/resources")
        for hotline in resp.json()["hotlines"]:
            for field in ("name", "number", "description", "available"):
                assert field in hotline, f"Missing field '{field}' in hotline"

    async def test_hotline_fields_are_non_empty_strings(self, client: AsyncClient):
        resp = await client.get("/api/v1/crisis/resources")
        for hotline in resp.json()["hotlines"]:
            for field in ("name", "number", "description", "available"):
                assert isinstance(hotline[field], str)
                assert len(hotline[field]) > 0

    async def test_breathing_exercise_has_required_fields(self, client: AsyncClient):
        resp = await client.get("/api/v1/crisis/resources")
        be = resp.json()["breathing_exercise"]
        for field in ("exercise_slug", "title", "description"):
            assert field in be, f"Missing field '{field}' in breathing_exercise"

    async def test_breathing_exercise_slug_is_non_empty(self, client: AsyncClient):
        resp = await client.get("/api/v1/crisis/resources")
        slug = resp.json()["breathing_exercise"]["exercise_slug"]
        assert isinstance(slug, str)
        assert len(slug) > 0

    async def test_message_is_non_empty_string(self, client: AsyncClient):
        resp = await client.get("/api/v1/crisis/resources")
        message = resp.json()["message"]
        assert isinstance(message, str)
        assert len(message) > 0

    async def test_breathing_exercise_slug_references_real_exercise(self, client: AsyncClient):
        """The slug in resources must point to a real exercise in the catalogue."""
        from app.services.exercise import get_exercise

        resp = await client.get("/api/v1/crisis/resources")
        slug = resp.json()["breathing_exercise"]["exercise_slug"]
        exercise = get_exercise(slug)
        assert exercise is not None, f"Slug '{slug}' not found in exercise catalogue"

    async def test_response_content_type_is_json(self, client: AsyncClient):
        resp = await client.get("/api/v1/crisis/resources")
        assert "application/json" in resp.headers.get("content-type", "")
