from app.schemas.resources import ResourceItem

_RESOURCES: list[ResourceItem] = [
    ResourceItem(
        id="breathing-guide",
        title="Hướng dẫn thở để giảm lo âu",
        type="article",
        duration_label="Đọc 5 phút",
        url=None,
    ),
    ResourceItem(
        id="sleep-meditation",
        title="Thiền giúp ngủ ngon hơn",
        type="audio",
        duration_label="Audio 12 phút",
        url=None,
    ),
    ResourceItem(
        id="grounding-techniques",
        title="Kỹ thuật hiện tại hóa khi lo lắng",
        type="article",
        duration_label="Đọc 7 phút",
        url=None,
    ),
    ResourceItem(
        id="morning-routine",
        title="Thói quen buổi sáng cho sức khoẻ tâm trí",
        type="video",
        duration_label="Video 8 phút",
        url=None,
    ),
    ResourceItem(
        id="cbt-intro",
        title="CBT là gì và nó giúp bạn thế nào?",
        type="article",
        duration_label="Đọc 6 phút",
        url=None,
    ),
]


def get_recommended_resources(limit: int = 2) -> list[ResourceItem]:
    return _RESOURCES[:limit]
