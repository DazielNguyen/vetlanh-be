from datetime import datetime, timezone

from app.schemas.community import CommunityFeaturedResponse

_MESSAGES: list[tuple[str, str]] = [
    ("Hôm nay tôi đã tập thở hộp lần đầu và cảm thấy bình tĩnh hơn nhiều. Cảm ơn cộng đồng đã chia sẻ!", "Lan A."),
    ("Đã check-in mood 7 ngày liên tiếp. Nhỏ thôi nhưng mình rất tự hào.", "Minh T."),
    ("Bài thiền 10 phút buổi sáng thay đổi cả ngày của mình. Ai chưa thử thì thử đi!", "Thu H."),
    ("Chia sẻ nhật ký giúp mình nhận ra pattern lo âu của bản thân. Rất hữu ích.", "Nam K."),
    ("Hôm nay khó khăn nhưng mình vẫn check-in. Đủ rồi.", "An P."),
]

# Illustrative counts — rotate deterministically by day so the value is stable
# within a calendar day and not jarring on page refresh.
_ACTIVE_COUNTS = [3, 5, 4, 6, 7, 4, 5]


def get_community_featured() -> CommunityFeaturedResponse:
    day_index = datetime.now(tz=timezone.utc).timetuple().tm_yday
    message, author = _MESSAGES[day_index % len(_MESSAGES)]
    active_count = _ACTIVE_COUNTS[day_index % len(_ACTIVE_COUNTS)]
    return CommunityFeaturedResponse(
        message=message,
        author_display=author,
        active_users_count=active_count,
    )
