# FE Handoff: FE-Missing Integration — Chatbot Sidebar, Insights & Prompts

> Branch: `dev`
> Date: 2026-06-06
> Source: `plans/FE-Missing/`

This document covers the BE endpoints that unblock the remaining mock-data items across the AI chatbot sidebar, mood tracker, assessments, and journal prompts.

---

## 1) Endpoint map

- `GET /api/v1/users/me/mood-summary` — Mood trend data for chatbot sidebar (sparse, last N days)
- `GET /api/v1/exercises/recommended` — Top N exercises for a given mood (chatbot sidebar)
- `GET /api/v1/mood/insights` — Personalised mood insights from historical check-in data
- `GET /api/v1/assessments/phq9/latest` — Latest PHQ-9 result for the current user
- `GET /api/v1/journal/prompts/daily` — Today's deterministic reflective prompt
- `GET /api/v1/journal/prompts/next` — Next prompt after the one currently shown
- `GET /api/v1/journal/prompts` — Full prompt list, optionally filtered by topic

---

## 2) Contracts

### Mood Summary (Chatbot Sidebar — LiveInsights.tsx)

`GET /api/v1/users/me/mood-summary`

**Auth:** Any authenticated user

**Query params:**
| Param | Type | Default | Note |
|-------|------|---------|------|
| `days` | `int` | `7` | Range: 1–90. Days of history to return |

**Response `data`:** `list[MoodSummaryEntry]` — sparse (only days with a check-in)

Each item:
- `date` — `YYYY-MM-DD` string
- `sentiment_score` — `int`, 1–5

```json
[
  { "date": "2026-06-04", "sentiment_score": 3 },
  { "date": "2026-06-06", "sentiment_score": 5 }
]
```

**FE usage:** Map `sentiment_score` to bar height (1→20%, 5→100%). Missing dates = no bar rendered.

---

### Recommended Exercises (Chatbot Sidebar — LiveInsights.tsx)

`GET /api/v1/exercises/recommended`

**Auth:** Any authenticated user

**Query params:**
| Param | Type | Default | Note |
|-------|------|---------|------|
| `mood` | `MoodFilter` | — | **Required.** One of: `anxious`, `sad`, `cant_sleep`, `need_energy`, `angry` |
| `limit` | `int` | `3` | Range: 1–10 |

**Response `data`:** `list[ExerciseResponse]`

Each item:
- `slug` — `string` — unique exercise identifier, use for navigation
- `title` — `string`
- `description` — `string`
- `category` — `"breathing" | "grounding" | "meditation" | "cbt" | "relaxation"`
- `duration_minutes` — `int`
- `mood_tags` — `list[MoodFilter]`
- `phases` — `list[{label, seconds}] | null` — breathing only
- `steps` — `list[{order, instruction, input_prompt?, tense_seconds?, release_seconds?}] | null` — grounding/PMR
- `audio_url` — `string | null` — CDN URL, meditation only
- `audio_options_minutes` — `list[int] | null`

```json
[
  {
    "slug": "478-breathing",
    "title": "Thở 4-7-8",
    "category": "breathing",
    "duration_minutes": 5,
    "mood_tags": ["anxious", "cant_sleep"],
    "phases": [{"label": "Hít vào", "seconds": 4}, {"label": "Nín thở", "seconds": 7}, {"label": "Thở ra", "seconds": 8}],
    "steps": null,
    "audio_url": null
  }
]
```

**FE usage:** Sidebar shows top 3 cards with `title`, `duration_minutes`, and link to `/exercises/{slug}`. Derive `mood` param from current user mood state (e.g., from latest mood check-in).

---

### Mood Insights

`GET /api/v1/mood/insights`

**Auth:** Any authenticated user

**Query params:** none

**Response `data`:** `InsightsResponse`

- `total_entries` — `int` — total check-ins on record
- `has_enough_data` — `bool` — `false` if fewer than 7 check-ins exist
- `insights` — `list[InsightItem]` — empty when `has_enough_data=false`

Each `InsightItem`:
- `type` — `"overall_average" | "day_of_week" | "factor_correlation"`
- `text` — `string` — human-readable insight, display as-is
- `delta` — `float | null` — `null` for `overall_average`; positive = improvement

```json
{
  "total_entries": 12,
  "has_enough_data": true,
  "insights": [
    { "type": "overall_average", "text": "Tâm trạng trung bình của bạn là 3.4/5", "delta": null },
    { "type": "day_of_week", "text": "Thứ Hai thường là ngày tâm trạng tốt nhất", "delta": 0.8 }
  ]
}
```

**FE usage:** Show "MoodInsights" section only when `has_enough_data=true`. When false, show a prompt encouraging more check-ins (e.g., "Hãy check-in thêm X ngày để xem phân tích").

---

### PHQ-9 Latest

`GET /api/v1/assessments/phq9/latest`

**Auth:** Any authenticated user

**Query params:** none

**Response `data`:** `PHQ9Result`

- `id` — `int`
- `score` — `int` — total score (0–27)
- `severity` — `"Minimal" | "Mild" | "Moderate" | "Severe"`
- `answers` — `list[int]` — 9 values, each 0–3
- `questions` — `list[string]` — 9 question texts (Vietnamese)
- `submitted_at` — ISO datetime string
- `suggested_goals` — `list[string]`
- `score_delta` — `int | null` — `current - previous`; `null` for first-ever assessment

**Errors:**
- `404` if no assessment has been submitted yet → show PHQ-9 form instead of result

---

### Journal Prompts — Daily

`GET /api/v1/journal/prompts/daily`

**Auth:** Any authenticated user

**Query params:** none

**Response `data`:** `DailyPromptResponse`

- `prompt` — `JournalPromptOut`
  - `id` — `int` — use as `current_id` when calling `/next`
  - `topic` — `string` — e.g. `"gratitude"`
  - `text` — `string` — the prompt sentence to display
- `topics` — `list[string]` — available topic slugs for the topic filter

```json
{
  "prompt": { "id": 7, "topic": "gratitude", "text": "Điều gì hôm nay khiến bạn biết ơn nhất?" },
  "topics": ["work_stress", "relationships", "self_compassion", "gratitude"]
}
```

---

### Journal Prompts — Next

`GET /api/v1/journal/prompts/next`

**Auth:** Any authenticated user

**Query params:**
| Param | Type | Default | Note |
|-------|------|---------|------|
| `current_id` | `int` | — | **Required.** ID of the prompt currently shown |

**Response `data`:** `JournalPromptOut` — same shape as `prompt` above

---

### Journal Prompts — List

`GET /api/v1/journal/prompts`

**Auth:** Any authenticated user

**Query params:**
| Param | Type | Default | Note |
|-------|------|---------|------|
| `topic` | `string` | `null` | Filter by topic slug. Omit for all prompts |

**Response `data`:** `list[JournalPromptOut]`

---

## 3) Error codes

| HTTP | Endpoint | Condition |
|------|----------|-----------|
| 422 | `GET /users/me/mood-summary` | `days` < 1 or > 90 |
| 422 | `GET /exercises/recommended` | `mood` missing or invalid value |
| 422 | `GET /journal/prompts/next` | `current_id` missing |
| 404 | `GET /assessments/phq9/latest` | No assessment submitted yet |

---

## 4) FE notes

**LiveInsights.tsx — Mood chart:**
- Call `GET /users/me/mood-summary?days=7` on mount. Response is sparse — dates with no entry are simply absent (do not fill with 0).
- The array can have 0–7 items. Render bars only for returned dates; leave other slots blank.

**LiveInsights.tsx — Recommended exercises:**
- `mood` query param is **required**. Derive it from the user's most recent check-in or a default (e.g., `anxious` as fallback).
- Sidebar needs only `slug`, `title`, `duration_minutes`. Do not request `limit > 3` in the sidebar.

**LiveInsights.tsx — Crisis button:**
- No BE endpoint. Use `tel:18006898` (Vietnam crisis hotline) or internal route `/services/crisis`. Product decision, not blocked by BE.

**MoodInsights.tsx:**
- Gate the component render on `has_enough_data`. The `insights` array may be empty even when `has_enough_data=true` in edge cases — guard against rendering an empty list.
- `delta` is `null` for `overall_average` type — always null-check before rendering trend arrow.

**PHQ-9 Latest:**
- 404 is a normal expected state for new users, not an error. `skipRetryOn(404)` is already set in `usePhq9Latest` — returns `null` data, shows the form.
- `submitted_at` can be displayed as the assessment date if needed.

**Journal prompts:**
- `/daily` returns a **deterministic** prompt per user per day (seeded by `user_id + date`). Refreshing the page returns the same prompt.
- To let users cycle prompts, call `/next?current_id={id}` — wraps around at the end of the list.
- `DailyPromptCard` has `if (!data) return null` guard — safe to render before data arrives.
