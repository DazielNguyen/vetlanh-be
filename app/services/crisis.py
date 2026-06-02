"""Crisis detection service — US-022.

Classifies user messages into three severity levels based on keyword matching.
Level 1: high anxiety  → suggest breathing exercise
Level 2: serious signs → show "talk to expert" banner
Level 3: crisis        → redirect to crisis screen immediately

Keyword list reviewed for Vietnamese mental-health context.
"""

from enum import IntEnum


class CrisisLevel(IntEnum):
    NONE = 0
    LEVEL_1_ANXIETY = 1
    LEVEL_2_SERIOUS = 2
    LEVEL_3_CRISIS = 3


# ---------------------------------------------------------------------------
# Keyword banks — ordered from least to most severe.
# Matching stops at the highest level found.
# ---------------------------------------------------------------------------

_LEVEL_1_KEYWORDS = [
    "lo lắng quá",
    "căng thẳng quá",
    "stress quá",
    "tim đập nhanh",
    "hồi hộp",
    "không thở được",
    "khó thở",
    "hoảng loạn",
    "panic",
    "lo âu",
    "bất an",
    "run sợ",
    "toát mồ hôi",
]

_LEVEL_2_KEYWORDS = [
    "không muốn sống",
    "chán sống",
    "sống để làm gì",
    "không còn ý nghĩa",
    "muốn biến mất",
    "muốn bỏ trốn tất cả",
    "không ai quan tâm",
    "cô đơn mãi",
    "không có tương lai",
    "tuyệt vọng",
    "vô vọng",
    "không lối thoát",
    "bế tắc",
    "không còn hy vọng",
    "không muốn gặp ai",
    "tự làm hại",
    "tự làm đau",
]

_LEVEL_3_KEYWORDS = [
    "muốn tự tử",
    "tự tử",
    "kết thúc cuộc đời",
    "kết thúc tất cả",
    "không muốn tồn tại",
    "muốn chết",
    "chết đi cho xong",
    "chết là hết",
    "uống thuốc ngủ",
    "nhảy xuống",
    "treo cổ",
    "cắt tay",
    "tự cắt",
    "tự làm mình chết",
    "không muốn sống nữa",
    "cuộc đời vô nghĩa và muốn kết thúc",
]


def detect_crisis_level(text: str) -> CrisisLevel:
    """Return the highest crisis level found in *text*.

    Matching is case-insensitive. Stops scanning higher levels once a match is
    found at a given level, but always checks higher levels first so that a
    level-3 phrase inside a longer message is never downgraded.
    """
    lower = text.lower()

    # Check from most severe to least — return immediately on first match.
    for keyword in _LEVEL_3_KEYWORDS:
        if keyword in lower:
            return CrisisLevel.LEVEL_3_CRISIS

    for keyword in _LEVEL_2_KEYWORDS:
        if keyword in lower:
            return CrisisLevel.LEVEL_2_SERIOUS

    for keyword in _LEVEL_1_KEYWORDS:
        if keyword in lower:
            return CrisisLevel.LEVEL_1_ANXIETY

    return CrisisLevel.NONE
