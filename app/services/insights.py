from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.mood import InsightItem, InsightsResponse
from app.services.mood import list_entries

_MIN_ENTRIES = 7
_MIN_SAMPLE = 2
_INSIGHT_THRESHOLD = 0.3

_VN_DAYS = [
    "thứ Hai",
    "thứ Ba",
    "thứ Tư",
    "thứ Năm",
    "thứ Sáu",
    "thứ Bảy",
    "Chủ nhật",
]


def _day_of_week_insight(entries, overall_avg: float) -> InsightItem | None:
    by_weekday: dict[int, list[int]] = defaultdict(list)
    for e in entries:
        by_weekday[e.date.weekday()].append(e.mood)

    wd_avgs = {
        wd: sum(moods) / len(moods)
        for wd, moods in by_weekday.items()
        if len(moods) >= _MIN_SAMPLE
    }
    if not wd_avgs:
        return None

    best_wd = max(wd_avgs, key=lambda k: wd_avgs[k])
    best_avg = wd_avgs[best_wd]
    if best_avg < overall_avg + _INSIGHT_THRESHOLD:
        return None

    delta = round(best_avg - overall_avg, 1)
    return InsightItem(
        type="day_of_week",
        text=(
            f"Tâm trạng của bạn thường tốt hơn vào {_VN_DAYS[best_wd]} "
            f"(cao hơn trung bình {delta:.1f} điểm)."
        ),
        delta=delta,
    )


def _factor_correlation_insight(entries, overall_avg: float) -> InsightItem | None:
    factor_moods: dict[str, list[int]] = defaultdict(list)
    for e in entries:
        for f in e.factors:
            factor_moods[f].append(e.mood)

    best_factor: str | None = None
    best_delta = _INSIGHT_THRESHOLD
    for factor, moods in factor_moods.items():
        if len(moods) < _MIN_SAMPLE:
            continue
        delta = sum(moods) / len(moods) - overall_avg
        if delta > best_delta:
            best_delta = delta
            best_factor = factor

    if best_factor is None:
        return None

    delta_r = round(best_delta, 1)
    # Factor strings are user-supplied free text (max_length=50, validated in MoodEntryCreate).
    # API returns JSON — HTML rendering is the client's responsibility (escape on render).
    return InsightItem(
        type="factor_correlation",
        text=(
            f"Những ngày có '{best_factor}', "
            f"tâm trạng của bạn cao hơn trung bình {delta_r:.1f} điểm."
        ),
        delta=delta_r,
    )


async def get_insights(db: AsyncSession, user_id: int) -> InsightsResponse:
    # 500 ≈ 1.5 years of daily check-ins — covers typical user history without unbounded queries.
    # Entries are ordered by date desc; oldest beyond 500 days are silently excluded.
    entries = await list_entries(db, user_id, limit=500)
    total = len(entries)

    if total < _MIN_ENTRIES:
        return InsightsResponse(
            total_entries=total,
            has_enough_data=False,
            insights=[],
        )

    overall_avg = sum(e.mood for e in entries) / total
    items: list[InsightItem] = [
        InsightItem(
            type="overall_average",
            text=f"Trong {total} ngày ghi lại, tâm trạng trung bình của bạn là {overall_avg:.1f}/5.",
        )
    ]

    dow = _day_of_week_insight(entries, overall_avg)
    if dow:
        items.append(dow)

    factor = _factor_correlation_insight(entries, overall_avg)
    if factor:
        items.append(factor)

    return InsightsResponse(
        total_entries=total,
        has_enough_data=True,
        insights=items,
    )
