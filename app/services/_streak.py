from datetime import date, timedelta

STREAK_LOOKBACK_DAYS = 90


def compute_streak(dates_with_entries: set[date], today: date) -> int:
    """Count consecutive days with an entry up to and including today.

    Returns 0 if neither today nor yesterday has an entry (no active streak).
    Allows a 1-day grace window so a user who hasn't checked in yet today
    doesn't lose a streak they built through yesterday.
    """
    if not dates_with_entries:
        return 0

    sorted_dates = sorted(dates_with_entries, reverse=True)
    most_recent = sorted_dates[0]

    # Grace window: streak must include today or yesterday
    if most_recent < today - timedelta(days=1):
        return 0

    streak = 1
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i - 1] - sorted_dates[i]).days == 1:
            streak += 1
        else:
            break
    return streak
