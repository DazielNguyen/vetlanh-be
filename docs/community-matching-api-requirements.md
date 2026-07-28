# BE API Requirements — Community 1-1 Anonymous Matching

**Date:** 2026-07-21
**Context:** Phase 7 of gaming-companion-redesign — replaces the previous static/fake "community" widget with a real opt-in 1-1 anonymous peer-matching feature, unlocked at user Level 5. This is the most safety-sensitive surface in the redesign (see `plan.md` Risks) — the moderation workflow below was explicitly approved by the product owner before FE implementation started.
**Frontend Status:** ✅ Frontend is fully implemented (opt-in flow, waiting room, conversation surface with report/block/exit, admin moderation queue) and ready to test against a mocked response. **Backend implementation required** for full end-to-end verification, including all REST endpoints below and the SignalR hub events.

---

## Overview

A user at Level 5+ can opt in to anonymous 1-1 peer matching from `/services/community`. Once matched, they see only the partner's anonymized handle — never a real name, email, or avatar — and can exchange plain-text messages. A persistently visible report/block/exit control is available at all times. Reporting always also exits the reporter from the conversation in the same action. Reported matches land in a new admin queue (`/admin/community-reports`) with an explicit 8-hour review SLA.

All pairing, anonymization, and moderation logic is backend-owned. The frontend only consumes the contract below.

---

## REST Endpoints

### 1. `GET /api/v1/community/match/status`
**Auth:** Required (Bearer token)
**Purpose:** Returns the caller's current opt-in/match state. Called once per app session (`staleTime: 5 min`) and re-synced instantly via SignalR push — not polled.

**Response (200 OK):**
```json
{
  "status": "opted_out",
  "match": null
}
```
or, when waiting for a partner:
```json
{ "status": "waiting", "match": null }
```
or, when actively matched:
```json
{
  "status": "matched",
  "match": {
    "matchId": "m_8f2a",
    "partnerHandle": "Người bạn ẩn danh #A3F2",
    "matchedAt": "2026-07-21T10:00:00Z"
  }
}
```

**Field notes:** `match` **must never** contain a partner user id, avatar URL, or any field resolvable back to the partner's real account — `matchId` is an opaque conversation identifier, not a user identifier, and `partnerHandle` is the only human-readable field.

### 2. `POST /api/v1/community/opt-in`
**Auth:** Required
**Purpose:** Explicit, user-confirmed opt-in (the frontend requires a confirmation step before calling this — never fires automatically). Immediately attempts pairing; if a partner is available, returns `status: "matched"` directly, otherwise `status: "waiting"`.
**Response (200 OK):** Same shape as `GET .../status`.

### 3. `POST /api/v1/community/opt-out`
**Auth:** Required
**Purpose:** Revokes opt-in. If currently matched, this also ends the active match (equivalent to exit). No request body.
**Response:** `204 No Content`

### 4. `GET /api/v1/community/match/{matchId}/messages`
**Auth:** Required (caller must be a participant in `matchId`)
**Purpose:** Message history for the given match. Fetched once per match (`staleTime: Infinity` on the frontend); new messages arrive only via the `ReceiveCommunityMessage` push event.
**Response (200 OK):**
```json
[
  { "id": "msg_1", "matchId": "m_8f2a", "content": "Chào bạn", "isMine": true, "createdAt": "2026-07-21T10:01:00Z" }
]
```
**Field notes:** `isMine` is resolved server-side relative to the caller's token — the frontend never compares user ids itself (it doesn't have the partner's id to compare against).

### 5. `POST /api/v1/community/match/{matchId}/messages`
**Auth:** Required
**Body:** `{ "content": "string" }`
**Purpose:** Sends a message. Frontend renders it optimistically before this resolves — on failure the frontend only logs a warning, it does not roll back or retry, so this endpoint should be reliable rather than requiring frontend-side retry logic.
**Response (200/201):** The persisted `CommunityMessage` object (used to reconcile the optimistic local copy).
**Content handling:** Return `content` as submitted — the frontend renders it as plain escaped text (no markdown/HTML interpretation on either side), so no sanitization-driven transformation of the string is expected back.

### 6. `POST /api/v1/community/match/{matchId}/exit`
**Auth:** Required
**Purpose:** Immediately ends the match for the caller. The **other** party must receive `CommunityMatchEnded` via SignalR so their UI updates without polling. No request body, no confirmation step on the frontend — this must succeed idempotently even if called twice.
**Response:** `204 No Content`

### 7. `POST /api/v1/community/match/{matchId}/block`
**Auth:** Required
**Purpose:** Ends the match for both parties. The blocking user's UI simply returns to the waiting state. The **blocked** party must receive a neutral `CommunityMatchEnded` event with **no indication they were blocked** (vs. a normal exit) — same generic "cuộc trò chuyện đã kết thúc" experience either way, to reduce retaliation risk.
**Response:** `204 No Content`
**Required BE rule (not FE-enforceable):** the two parties in a block must be excluded from being re-matched with each other for a cooldown window. Exact cooldown duration is a BE decision — flagging this as a requirement, not proposing a specific value.

### 8. `POST /api/v1/community/match/{matchId}/report`
**Auth:** Required
**Body:** `{ "reason"?: "string" }` (optional — frontend allows submitting with no reason text)
**Purpose:** Creates an entry in the admin moderation queue **and** ends the match for the reporting user in the same action (equivalent to exit, from the reporter's side only — the reported party's session is not necessarily ended by this call alone, pending admin review). The frontend already treats this as combined report+exit locally; the backend should record `reported_at` and compute `sla_deadline` = `reported_at + 8h` at creation time.
**Response:** `204 No Content`

---

## SignalR Hub Events (existing `/hubs/app` connection)

Reuses the hub connection already established for Phase 5 check-ins — no new connection, just new event names on the existing one.

| Event | Payload | Fired when |
|---|---|---|
| `ReceiveCommunityMatch` | `CommunityMatch` (see `.../status` shape) | A waiting user gets paired with a partner |
| `CommunityMatchEnded` | `{ "matchId": "string" }` | Either party exits/blocks, or an admin unmatches the pair |
| `ReceiveCommunityMessage` | `CommunityMessage` (see message shape above) | A new message is sent in a match the recipient is part of |

All three should only be sent to the specific user(s) affected — never broadcast to all connected clients.

---

## Admin Endpoints (`/admin/community-reports` moderation queue)

### `GET /api/v1/admin/community/reports?status=open|resolved`
**Auth:** Admin only (same admin-token check as other `/admin/*` endpoints)
**Response (200 OK):**
```json
[
  {
    "id": "r_1",
    "matchId": "m_8f2a",
    "reporterHandle": "Người bạn ẩn danh #A3F2",
    "reportedHandle": "Người bạn ẩn danh #B991",
    "reason": "Ngôn từ khó chịu",
    "reportedAt": "2026-07-21T10:05:00Z",
    "slaDeadline": "2026-07-21T18:05:00Z",
    "status": "open"
  }
]
```
**Field notes:** `slaDeadline` = `reportedAt + 8 hours`, computed by the backend — the frontend only displays an "overdue" badge when `now > slaDeadline`, it does not compute the deadline itself.

### `POST /api/v1/admin/community/reports/{id}/warn`
Marks the report resolved and issues a warning to the reported user. Returns the updated `CommunityReport` (`status: "resolved"`).

### `POST /api/v1/admin/community/reports/{id}/unmatch`
Marks the report resolved and force-ends the associated match if still active (fires `CommunityMatchEnded` to both parties via SignalR). Returns the updated `CommunityReport`.

### `POST /api/v1/admin/community/reports/{id}/ban`
Marks the report resolved and bans the reported user from the community-matching feature (opt-in should be rejected or silently no-op for a banned user going forward). Returns the updated `CommunityReport`.

---

## Error Cases
- `401` — Unauthorized (invalid/expired token)
- `403` — Caller is not a participant of `matchId` (messages/exit/block/report endpoints)
- `404` — `matchId` or report `id` not found, or already resolved/ended (frontend treats this as "already handled," not a hard error)

---

## Implementation Checklist

### Backend Tasks
- [ ] Implement `GET/POST /api/v1/community/opt-in`, `/opt-out`, `/match/status` with the three-state model (`opted_out` / `waiting` / `matched`)
- [ ] Implement matching/pairing logic (BE-owned — algorithm unspecified by this doc, any fair-queue approach is acceptable for MVP)
- [ ] Implement message send/history endpoints, resolving `isMine` server-side per caller token
- [ ] Implement exit/block/report endpoints — **all three must be idempotent and must not require the calling user's match to still be active to succeed**
- [ ] Wire `ReceiveCommunityMatch`, `CommunityMatchEnded`, `ReceiveCommunityMessage` on the existing `/hubs/app` SignalR hub, targeted to the specific affected user(s) only
- [ ] Enforce block-cooldown: two parties in a `block` action must not be re-matched with each other for a BE-defined cooldown window
- [ ] Implement the 8-hour SLA computation (`reportedAt + 8h`) at report-creation time — do not leave this to the frontend
- [ ] Implement admin queue endpoints (`GET reports`, `warn`, `unmatch`, `ban`) reusing the same admin-token auth already enforced on other `/admin/*` routes
- [ ] Ensure no endpoint response anywhere in this contract includes the partner's real user id, username, email, or avatar URL — verify by inspecting raw network responses, not just the rendered UI

---

## Testing Notes for FE Team

Until backend implements this feature:

1. **Mock the responses:** Stub `fetchCommunity.*` / `fetchAdmin.get/warn/unmatch/banCommunityReport` in tests to exercise `opted_out` / `waiting` / `matched` states and the admin queue's open/resolved tabs.
2. **Integration test once BE ships:**
   - Two test accounts opt in and confirm they get matched (or one lands in `waiting` if the other opts out first)
   - Confirm no partner-identity field leaks anywhere in DevTools Network tab
   - Confirm exit/block/report reflect on **both** sides via SignalR without a page refresh
   - Confirm reporting immediately exits the reporter and appears in the admin queue within the SLA window
   - Confirm a blocked pair cannot be immediately re-matched

---

## Confirmed Specifications

| Item | Value |
|------|-------|
| Opt-in | Explicit POST after frontend confirmation step — never default-on |
| Match states | `opted_out` \| `waiting` \| `matched` |
| Real-time transport | Existing `/hubs/app` SignalR connection, 3 new event names |
| Anonymization | `partnerHandle` only — no user id/avatar/email anywhere in the contract |
| Report behavior | Combined report + exit in one action; creates admin queue entry |
| Admin SLA | 8 hours from `reportedAt`, BE-computed |
| Block behavior | Symmetric match-end; blocked party sees a neutral message, not "you were blocked" |
| Re-match cooldown after block | Required BE rule, exact duration is a BE decision |
| Peer message rendering | Plain escaped text only — no markdown/HTML pipeline on either side |
