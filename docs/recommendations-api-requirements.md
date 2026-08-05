# BE API Requirements — AI-Personalized Dashboard Recommendation

**Date:** 2026-07-21
**Context:** Phase 6 of gaming-companion-redesign — dashboard shows one AI-derived recommendation card, distinct from the existing static "top exercises" card, drawing on the user's mood/journal/PHQ-9 history.
**Frontend Status:** ✅ Frontend component (`AIRecommendationCard`) and hook (`usePersonalizedRecommendation`) are implemented and ready to test against a mocked response. **Backend implementation required** for full end-to-end verification.
**Backend Status:** ❌ Not implemented yet — verified live against production API on 2026-08-04, `GET /api/v1/dashboard/personalized-recommendation` still returns `404 {"detail":"Not Found"}`. Not urgent/blocking: the frontend already treats 404 as the expected "not shipped yet" case (`retry: skipRetryOn(404)` in `hooks/useRecommendation.ts`), so the card just renders nothing until this ships — no user-facing error.

---

## Overview

The frontend already has a static "top-N exercises" card (`QuickReliefCard`, `GET /api/v1/exercises/recommended`) with no personalization or explanation. Phase 6 adds a second, distinct card that surfaces exactly **one** recommendation derived from the user's own mood history, journal entries, and latest PHQ-9 result, along with a short human-readable rationale (e.g. "vì tuần này bạn có nhiều ngày căng thẳng hơn").

This derivation happens entirely server-side — the backend already has (or can access) mood/journal/PHQ-9 data with better context than the frontend does, so the frontend does not re-fetch and re-analyze raw history itself. It calls one endpoint and renders whatever comes back, or falls back to the existing static card if nothing is returned.

---

## REST Endpoint: Fetch Personalized Recommendation

### Endpoint
**`GET /api/v1/dashboard/personalized-recommendation`**

### Auth
Required (Bearer token)

### Purpose
Returns a single AI-derived recommendation (one exercise or library item) based on the user's recent mood entries, journal entries, and latest PHQ-9 result, plus a short rationale explaining why it was chosen. Returns `null` if there isn't enough data yet to personalize (new user, no mood/journal entries).

### Response (200 OK)
```json
{
  "title": "string",
  "rationale": "string",
  "url": "string"
}
```
or, when there's not enough data to personalize yet:
```json
null
```

### Example
```json
{
  "title": "Bài tập thở hộp 4-4-4",
  "rationale": "Vì tuần này bạn có nhiều ngày căng thẳng hơn tuần trước",
  "url": "/services/exercises/box-breathing"
}
```

### Field Notes
- `title` — short, human-readable name of the recommended content (exercise or library item)
- `rationale` — one short Vietnamese sentence explaining why this was picked, referencing the signal that drove it (mood trend, journal theme, PHQ-9 change). Avoid clinical/alarming phrasing since PHQ-9 data is sensitive — keep it supportive, not diagnostic.
- `url` — the **final relative frontend route** to navigate to when tapped, already resolved by the backend (e.g. `/services/exercises/{slug}` or `/services/library/{id}`). The frontend does not branch on content type — it just renders `<Link href={url}>`, so the backend is free to point at any route shape without a frontend change. **Must be a same-origin relative path starting with a single `/`** (not `//`, not an absolute `https://` URL, not a `javascript:`/`data:` scheme) — the frontend validates this and renders nothing if it isn't, as a defense-in-depth measure against a compromised/misconfigured response.

### Error Cases
- `401` — Unauthorized (invalid/expired token)
- `200` with `null` body — not an error; means "no personalization available yet," and the frontend falls back to the existing static suggested-exercise card

### Frontend Notes
- Called with React Query `staleTime: 24h` and no `refetchInterval` — refreshes on the next app open after a day has passed, not polled
- Query key: `["recommendation", "personalized"]` in `hooks/useRecommendation.ts`
- On `isLoading`: card shows a skeleton
- On `null` or error: card renders nothing (`return null`) — the adjacent `QuickReliefCard` (static top-N exercises) remains visible as the fallback, so the user never sees an empty gap

---

## Implementation Checklist

### Backend Tasks
- [ ] Implement `GET /api/v1/dashboard/personalized-recommendation`:
  - Reads the current user's mood entries (last ~7-14 days), recent journal entries, and latest PHQ-9 result
  - Applies derivation logic (rule-based or model-based) to pick one exercise or library item
  - Generates a short supportive Vietnamese rationale referencing the signal used
  - Returns `null` (200 OK, empty body semantics) when there's insufficient history to personalize — do NOT return a 404 or error for this case
  - Resolves the final frontend route and returns it as `url` (e.g. `/services/exercises/{slug}`, `/services/library/{id}`)

- [ ] Decide and document the "insufficient data" threshold (e.g. fewer than N mood entries or no PHQ-9 result yet) so behavior is consistent and testable

- [ ] Rate limiting not required — this is a low-frequency, cached-for-a-day read, not a hot path

---

## Testing Notes for FE Team

Until backend implements this endpoint:

1. **Mock the response:** Stub `fetchRecommendation.getPersonalized` in tests, or intercept the request in dev tools, to return a sample recommendation object or `null` to verify both the populated and fallback states.
2. **Integration test:** Once backend ships, coordinate with backend team to:
   - Verify a user with rich mood/journal/PHQ-9 history receives a plausible, non-generic recommendation
   - Verify a fresh user with no history receives `null` and sees only the static `QuickReliefCard`
   - Verify tapping the card navigates to the exact `url` returned

---

## Confirmed Specifications

| Item | Value |
|------|-------|
| Endpoint | `GET /api/v1/dashboard/personalized-recommendation` |
| Response on success | `{ title, rationale, url }` |
| Response on insufficient data | `null` (200 OK), not an error |
| Refresh strategy | `staleTime: 24h`, no polling |
| Routing | Backend returns a ready-to-use relative `url`; frontend does not branch on content type |
| Fallback UI | Existing static `QuickReliefCard` remains visible when this card renders nothing |

---

## Implementation Addendum (2026-08-05)

Implemented in `app/services/recommendation.py` (selection logic) and
`app/api/v1/endpoints/dashboard.py` (route). Two deliberate deviations from
the spec above, plus the concrete rules actually implemented:

- **Exercise-only, no "library item".** This codebase has no separate
  library-item content model — every recommendation resolves to an
  `app/services/exercise.py` catalog entry, so `url` is always
  `/services/exercises/{slug}`.
- **No journal-content signal.** Only mood entries (`MoodEntry`) and PHQ-9
  results (`Assessment`) are read. Journal text is `EncryptedText` and
  reading it would require decryption plus non-LLM NLP for a single
  dashboard card — out of proportion, and reopens the sensitive-data
  question the "no LLM" decision was meant to close.
- **Eligibility ("insufficient data") threshold:** the user qualifies if they
  have ≥3 mood entries in the last 7 days, or have ever submitted a PHQ-9 —
  otherwise the endpoint returns `null`.
- **Signal precedence** (first match wins): PHQ-9 Moderate/Severe taken
  within the last 30 days → mood-trend decline (current vs. prior 7-day
  average, ≥3% delta) → PHQ-9 Mild → most recent mood entry. A stale
  Moderate/Severe result older than 30 days does not fire; a since-recovered
  user falls through to the next rule instead of being locked into
  calming-only content indefinitely.
- **Clinical safety:** the PHQ-9 Moderate/Severe branch only ever selects
  from a small hardcoded calming/grounding allow-list — never an
  "energizing" exercise from the general mood-tag catalog. Rationale text is
  a closed set of static Vietnamese sentences with no interpolation of
  scores, severity labels, or journal text.
- **Not crisis detection.** This endpoint never reads PHQ-9 item 9
  (suicidal ideation) and provides no safety-net coverage — that remains
  `app/services/crisis.py`'s responsibility.
