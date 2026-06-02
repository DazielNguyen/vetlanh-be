"""Reflective journal prompt suggestions — US-029."""

import hashlib
from datetime import date

_PROMPTS: list[dict] = [
    # Stress công việc
    {"id": 1, "topic": "work_stress", "text": "Điều gì ở công việc hôm nay khiến bạn cảm thấy nặng nề nhất?"},
    {"id": 2, "topic": "work_stress", "text": "Nếu bạn có thể thay đổi một điều trong ngày làm việc hôm nay, đó là gì?"},
    {"id": 3, "topic": "work_stress", "text": "Khi công việc trở nên quá tải, bạn thường tự nhủ điều gì với bản thân?"},
    {"id": 4, "topic": "work_stress", "text": "Bạn đã hoàn thành được điều gì trong tuần này dù áp lực rất lớn?"},
    {"id": 5, "topic": "work_stress", "text": "Ranh giới nào giữa công việc và cuộc sống riêng mà bạn muốn thiết lập?"},
    {"id": 6, "topic": "work_stress", "text": "Điều gì trong công việc mang lại cho bạn cảm giác có ý nghĩa?"},
    {"id": 7, "topic": "work_stress", "text": "Bạn cần điều gì để cảm thấy được hỗ trợ hơn ở nơi làm việc?"},
    {"id": 8, "topic": "work_stress", "text": "Có kỳ vọng nào bạn đặt ra cho bản thân mà bạn muốn điều chỉnh lại không?"},
    # Mối quan hệ
    {"id": 9, "topic": "relationships", "text": "Ai trong cuộc sống của bạn khiến bạn cảm thấy được lắng nghe?"},
    {"id": 10, "topic": "relationships", "text": "Có điều gì bạn muốn nói với ai đó nhưng vẫn chưa nói được không?"},
    {"id": 11, "topic": "relationships", "text": "Mối quan hệ nào đang tiêu hao năng lượng của bạn? Điều đó dạy bạn điều gì?"},
    {"id": 12, "topic": "relationships", "text": "Bạn cảm thấy thế nào khi được quan tâm? Bạn có dễ dàng nhận sự quan tâm không?"},
    {"id": 13, "topic": "relationships", "text": "Lần cuối bạn thực sự kết nối sâu với ai đó là khi nào?"},
    {"id": 14, "topic": "relationships", "text": "Có ranh giới nào trong mối quan hệ mà bạn cần đặt ra hoặc củng cố không?"},
    {"id": 15, "topic": "relationships", "text": "Bạn muốn người thân hiểu hơn về bạn điều gì?"},
    {"id": 16, "topic": "relationships", "text": "Khi mâu thuẫn xảy ra, bạn thường phản ứng thế nào? Bạn muốn thay đổi gì?"},
    # Tự thương (self-compassion)
    {"id": 17, "topic": "self_compassion", "text": "Bạn sẽ nói gì với người bạn thân nếu họ đang trong tình huống của bạn?"},
    {"id": 18, "topic": "self_compassion", "text": "Điều gì bạn hay chỉ trích bản thân mà thực ra không xứng đáng bị chỉ trích?"},
    {"id": 19, "topic": "self_compassion", "text": "Bạn đã vượt qua được điều gì khó khăn mà bản thân không ngờ tới?"},
    {"id": 20, "topic": "self_compassion", "text": "Hôm nay bạn đã chăm sóc bản thân theo cách nào, dù nhỏ?"},
    {"id": 21, "topic": "self_compassion", "text": "Điều gì khiến bạn cảm thấy xấu hổ? Bạn có thể nhìn nhận nó bằng sự nhẹ nhàng hơn không?"},
    {"id": 22, "topic": "self_compassion", "text": "Bạn cần được tha thứ điều gì từ chính mình?"},
    {"id": 23, "topic": "self_compassion", "text": "Điểm mạnh nào của bạn đã giúp bạn vượt qua giai đoạn khó khăn gần đây?"},
    {"id": 24, "topic": "self_compassion", "text": "Nếu tự thương là một người bạn, họ sẽ nhắn gì cho bạn tối nay?"},
    # Biết ơn
    {"id": 25, "topic": "gratitude", "text": "Ba điều nhỏ đã xảy ra hôm nay mà bạn biết ơn là gì?"},
    {"id": 26, "topic": "gratitude", "text": "Ai đó đã làm cho cuộc sống của bạn tốt hơn mà bạn chưa kịp nói lời cảm ơn?"},
    {"id": 27, "topic": "gratitude", "text": "Điều gì trong cơ thể hoặc sức khỏe của bạn mà bạn thường bỏ qua nhưng thực sự đáng trân trọng?"},
    {"id": 28, "topic": "gratitude", "text": "Khoảnh khắc bình yên nào trong tuần này bạn muốn ghi nhớ?"},
    {"id": 29, "topic": "gratitude", "text": "Điều gì trong cuộc sống hiện tại của bạn mà 5 năm trước bạn đã ước ao có được?"},
    {"id": 30, "topic": "gratitude", "text": "Khó khăn nào bạn đang đối mặt mà cũng mang lại cho bạn điều gì đó có giá trị?"},
    {"id": 31, "topic": "gratitude", "text": "Thiên nhiên, âm nhạc, hoặc nghệ thuật nào đã chạm đến bạn gần đây?"},
    {"id": 32, "topic": "gratitude", "text": "Điều gì trong thói quen hàng ngày của bạn mang lại cảm giác ổn định và an toàn?"},
]

_TOPICS = ["work_stress", "relationships", "self_compassion", "gratitude"]


def get_daily_prompt(user_id: int, today: date | None = None) -> dict:
    """Return a deterministic daily prompt for the user based on user_id + date."""
    if today is None:
        today = date.today()
    seed = f"{user_id}:{today.isoformat()}"
    digest = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    return _PROMPTS[digest % len(_PROMPTS)]


def get_next_prompt(current_id: int) -> dict:
    """Return the next prompt after current_id, wrapping around."""
    ids = [p["id"] for p in _PROMPTS]
    try:
        idx = ids.index(current_id)
    except ValueError:
        idx = -1
    return _PROMPTS[(idx + 1) % len(_PROMPTS)]


def list_by_topic(topic: str | None) -> list[dict]:
    if topic is None:
        return _PROMPTS
    return [p for p in _PROMPTS if p["topic"] == topic]
