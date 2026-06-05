# FE Handoff: Sprint 4 — Polish & Scale

> Branch: `dev`
> Date: 2026-06-06

## 1) Endpoint map

- `GET /api/v1/mood/heatmap` — sparse mood calendar for a given year/month (US-015)
- `GET /api/v1/exercises` — list all exercises; now includes PMR (`pmr-7-groups`) with new `relaxation` category (US-021)
- `GET /api/v1/exercises/{slug}` — exercise detail; `ExerciseStep` now has optional `tense_seconds` / `release_seconds` fields (US-021)
- `GET /api/v1/notifications/exercise-reminder` — check whether to show a daily exercise prompt (US-032)
- `GET /api/v1/notifications/preference` — get notification preferences; now includes `exercise_enabled` + `exercise_reminder_time` (US-032)
- `PATCH /api/v1/notifications/preference` — update preferences; now accepts `exercise_enabled` + `exercise_reminder_time` (US-032)

> **Breaking change (US-030):** `GET /api/v1/journal?q=<keyword>` no longer matches against entry content — search is title-only after journal encryption.

---

## 2) Contracts

### GET /api/v1/mood/heatmap

`GET /api/v1/mood/heatmap`

**Auth:** any authenticated user (Bearer JWT)

**Query params:**
| Param | Type | Required | Constraints |
|-------|------|----------|-------------|
| `year` | integer | yes | 2000–2100 |
| `month` | integer | yes | 1–12 |

**Response `data`:**
```json
{
  "year": 2026,
  "month": 6,
  "days": [
    { "date": "2026-06-01", "mood_score": 4 },
    { "date": "2026-06-03", "mood_score": 2 }
  ]
}
```

- `days` is **sparse** — only dates that have a mood entry are included. Days with no entry are omitted.
- `mood_score`: integer 1–5.
- Empty month returns `"days": []`.

---

### GET /api/v1/exercises (updated — PMR added)

`GET /api/v1/exercises`

**Auth:** any authenticated user

**Query params (unchanged):**
| Param | Type | Default | Note |
|-------|------|---------|------|
| `mood` | string (enum) | — | Filter: `anxious`, `sad`, `cant_sleep`, `need_energy`, `angry` |
| `category` | string (enum) | — | Filter: `breathing`, `grounding`, `meditation`, `cbt`, **`relaxation`** (new) |

**Response — `ExerciseStep` schema change:**
```json
{
  "slug": "pmr-7-groups",
  "title": "...",
  "category": "relaxation",
  "steps": [
    {
      "order": 1,
      "instruction": "Nắm chặt hai nắm tay...",
      "input_prompt": null,
      "tense_seconds": 7,
      "release_seconds": 30
    }
  ]
}
```

- `tense_seconds` and `release_seconds` are **`null`** for all non-PMR exercises — handle gracefully.
- PMR (`pmr-7-groups`) has exactly 7 steps.
- `pmr-7-groups` appears under `mood=anxious` and `mood=angry` filters.

---

### GET /api/v1/notifications/exercise-reminder

`GET /api/v1/notifications/exercise-reminder`

**Auth:** any authenticated user

**Response:**
```json
{
  "should_notify": true,
  "reason": "ok"
}
```

`reason` values (informational — for debugging only, do not display to user):
| `should_notify` | `reason` |
|-----------------|----------|
| `true` | `"ok"` |
| `false` | `"exercise notifications disabled"` |
| `false` | `"quiet hours"` |
| `false` | `"not yet reminder time"` |
| `false` | `"already exercised today"` |

---

### GET /api/v1/notifications/preference (updated)

`GET /api/v1/notifications/preference`

**Auth:** any authenticated user

**Response:**
```json
{
  "reminder_time": "08:00",
  "enabled": true,
  "quiet_start": "22:00",
  "quiet_end": "07:00",
  "exercise_enabled": true,
  "exercise_reminder_time": "08:00"
}
```

- `exercise_enabled`: boolean, server default `true`.
- `exercise_reminder_time`: HH:MM string, server default `"08:00"`.

---

### PATCH /api/v1/notifications/preference (updated)

`PATCH /api/v1/notifications/preference`

**Auth:** any authenticated user

**Body (all fields optional):**
```json
{
  "reminder_time": "09:00",
  "enabled": true,
  "quiet_start": "22:00",
  "quiet_end": "07:00",
  "exercise_enabled": false,
  "exercise_reminder_time": "07:30"
}
```

Validation rules:
- `exercise_reminder_time` must match `HH:MM` format with valid hour (0–23) and minute (0–59) — same rule as `reminder_time`.
- `"25:00"` or `"08:70"` → HTTP 422.

**Response:** same shape as `GET /preference`.

---

## 3) Error codes

| HTTP | When |
|------|------|
| 401 | Missing or expired JWT on any endpoint |
| 422 | `year` out of 2000–2100, `month` out of 1–12 (heatmap) |
| 422 | `exercise_reminder_time` or `reminder_time` invalid format/range (PATCH preference) |

---

## 4) FE notes

- **Heatmap:** fetch once per month on calendar open; do NOT re-fetch on every day tap. Cache by `year+month` key.
- **PMR timer UI:** `tense_seconds` (7s) and `release_seconds` (30s) are the timer durations — show a countdown while the user performs each step. Non-PMR exercises have `null` for both fields, so guard with `if (step.tense_seconds != null)`.
- **`relaxation` category:** this is a new enum value. If the app serialises `ExerciseCategory` strictly, update the allowed values list to include `"relaxation"`.
- **Exercise reminder vs mood reminder:** two separate endpoints — poll both independently. `GET /exercise-reminder` is for exercise, `GET /should-notify` is for mood check-in.
- **Journal search regression:** `GET /api/v1/journal?q=<text>` now searches title only. If the app had a "search content" UX, update copy to say "search by title". Results for content keywords will return empty — this is expected behaviour, not a bug.
- **Notification preference migration:** existing users will have `exercise_enabled=true` and `exercise_reminder_time="08:00"` automatically (server defaults applied by DB migration). No special handling needed on first app launch.
