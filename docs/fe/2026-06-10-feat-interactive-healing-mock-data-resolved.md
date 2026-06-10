# FE Handoff: Interactive Healing Services — Mock Data Resolved

> Branch: `dev`
> Date: 2026-06-10

This closes out all 5 items in `docs/mock-data-remaining-interactive-healing.md`. All required data is now available from BE — remaining work is FE-side only (replace hardcoded constants with API reads).

## 1) Endpoint map

- `GET /api/v1/exercises/feeling-options` — **new**, public — post-session feeling options (key/label/emoji)
- `GET /api/v1/exercises/mood-filters` — **changed**, public — now includes `emoji` field
- `PATCH /api/v1/exercises/logs/{log_id}` — existing — record post-session feeling on a log
- `GET /api/v1/dashboard` — **changed** — now includes `stress_level` and `stress_trend_text`
- `GET /api/v1/exercises/{slug}` — unchanged, but see note in §4 about `phases[]`

## 2) Contracts

### GET /api/v1/exercises/feeling-options

`GET /api/v1/exercises/feeling-options`

**Auth:** none (public)

**Response `data`:** array of
- `key` — string, one of `much_better` | `better` | `same` | `worse`
- `label` — string, Vietnamese display label
- `emoji` — string

```json
[
  { "key": "much_better", "label": "Rất nhẹ", "emoji": "😌" },
  { "key": "better", "label": "Nhẹ hơn", "emoji": "😊" },
  { "key": "same", "label": "Bình thường", "emoji": "😐" },
  { "key": "worse", "label": "Vẫn căng", "emoji": "😣" }
]
```

### GET /api/v1/exercises/mood-filters (now with emoji)

`GET /api/v1/exercises/mood-filters`

**Auth:** none (public)

**Response `data`:** array of
- `key` — string (mood filter enum: `anxious`, `sad`, `cant_sleep`, `need_energy`, `angry`)
- `label` — string
- `emoji` — string (new field)

```json
[
  { "key": "anxious", "label": "Lo âu", "emoji": "😰" },
  { "key": "sad", "label": "Buồn bã", "emoji": "😢" },
  { "key": "cant_sleep", "label": "Mất ngủ", "emoji": "🌙" },
  { "key": "need_energy", "label": "Cần năng lượng", "emoji": "⚡" },
  { "key": "angry", "label": "Tức giận", "emoji": "😤" }
]
```

### PATCH /api/v1/exercises/logs/{log_id}

`PATCH /api/v1/exercises/logs/{log_id}`

**Auth:** any authenticated user (must own the log — 404 if not found or not owned)

**Body:**
```json
{ "post_session_feeling": "much_better" }
```

Validation rules:
- `post_session_feeling` — required, one of `much_better` | `better` | `same` | `worse` (use `key` from `feeling-options`)

**Response `data`:** `ExerciseLogResponse`
- `id` — int
- `exercise_slug` — string
- `duration_seconds` — int
- `post_session_feeling` — string | null
- `created_at` — datetime

### GET /api/v1/dashboard (stress_level + stress_trend_text)

`GET /api/v1/dashboard`

**Auth:** any authenticated user

**Response `data`:** new fields added to existing `DashboardResponse`
- `stress_level` — `"low" | "medium" | "high" | null` — derived from average mood this week; `null` when no mood entries this week
- `stress_trend_text` — string | null — e.g. `"tốt hơn ~12% tuần này"`, `"xấu hơn ~8% tuần này"`, `"ổn định tuần này"`, or `null` when not enough data (no current or previous week average)

## 3) Error codes

| HTTP | code | message |
|------|------|---------|
| 404 | — | `Exercise not found` (PATCH on a log not owned by/not found for the user) |

## 4) FE notes

- **Feeling picker (item 2 & 3):** fetch `feeling-options` once (cacheable, public), render the 4 buttons from it instead of the hardcoded `FEELINGS` array. On selection, call `PATCH /exercises/logs/{log_id}` with `{ "post_session_feeling": key }` — `log_id` comes from the response of `POST /exercises/log` made when the session completed.
- **Mood emoji map (item 4):** drop `EMOJI_MOOD_MAP` in `ExerciseList.tsx`; use `emoji` directly from `mood-filters` response for every key — no more "5-key map vs text pill" branching needed.
- **StressChart (item 5):** render `stress_level` → label mapping FE-side (`low` → "Thấp", `medium` → "Trung bình", `high` → "Cao") and show `stress_trend_text` verbatim. Both can be `null` — handle with a fallback/empty state.
- **Breathing timing (item 1) — no schema change:** `ExerciseResponse.phases[]` (`{ label, seconds }`) already carries per-exercise breathing timing and was *not* changed this session. Replace `BREATH_INHALE/HOLD/EXHALE` constants with a loop over `exercise.phases` — this works for box-breathing (4 phases), 4-7-8 (3 phases), and coherent breathing (2 phases) without any FE-side special-casing per exercise.
