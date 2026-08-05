"""
Unit tests for the rule-based emotion classifier's Vietnamese negation handling.

Bug (docs/service-chat-agent-context-tools-api-requirements.md, "Known issue —
inverted emotion label observed in production 2026-08-05"): plain substring
matching on bare root words ("vui", "tốt", "ổn") let negated phrases like
"không vui" (not happy) match the un-negated keyword and get classified as
"happy". Fixed by checking for a Vietnamese negator immediately before the
matched keyword.
"""

from app.ml.text_model import _rule_based_predict, _extract_text_signals


def _predict(text: str) -> dict:
    return _rule_based_predict(text, _extract_text_signals(text))


class TestNegatedHappyKeyword:
    def test_reported_production_case_not_classified_happy(self):
        result = _predict("ĐANG KHÔNG VUI")
        assert result["emotion"]["label"] != "happy"

    def test_khong_vui_lowercase_not_classified_happy(self):
        result = _predict("hôm nay tôi không vui")
        assert result["emotion"]["label"] != "happy"

    def test_khong_on_not_classified_happy(self):
        result = _predict("dạo này cảm thấy không ổn")
        assert result["emotion"]["label"] != "happy"

    def test_khong_tot_does_not_reduce_depression_score_as_positive(self):
        # "không tốt" must not count as a _POSITIVE_WORDS hit that offsets
        # genuine negative signals in the same message — it should score the
        # same as if the positive word were absent entirely.
        with_negated_positive = _predict("buồn quá, mọi thứ không tốt cả")
        without_positive_word = _predict("buồn quá, mọi thứ tệ cả")
        assert (
            with_negated_positive["depression_risk"]["phq_estimate"]
            == without_positive_word["depression_risk"]["phq_estimate"]
        )


class TestUnnegatedHappyStillWorks:
    def test_plain_vui_classified_happy(self):
        result = _predict("hôm nay tôi rất vui")
        assert result["emotion"]["label"] == "happy"

    def test_plain_tot_counts_as_positive(self):
        result = _predict("mọi thứ đều tốt")
        assert result["depression_risk"]["level"] == "none"


class TestNegationWindowDoesNotOverreach:
    def test_negator_far_before_keyword_does_not_suppress_it(self):
        # "không" appears, but far enough before "vui" that it doesn't negate it —
        # should still be read as happy, not suppressed.
        result = _predict("tôi không biết tại sao nhưng hôm nay thấy vui")
        assert result["emotion"]["label"] == "happy"
