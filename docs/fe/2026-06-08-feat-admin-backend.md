# FE Handoff: Admin Backend

> Branch: `dev`
> Date: 2026-06-08
> Commit: `80911f3`

## 1) Endpoint map

**Admin routes** — require `Authorization: Bearer <admin-token>` (403 if not in `ADMIN_USERS`)

- `GET /api/v1/admin/stats` — dashboard stats summary (users, revenue, errors)
- `GET /api/v1/admin/users` — paginated + searchable user list with subscription status
- `GET /api/v1/admin/subscriptions/pending` — pending subscription requests
- `GET /api/v1/admin/subscriptions/active` — currently active subscriptions
- `POST /api/v1/admin/subscriptions/{id}/grant` — approve a pending subscription
- `POST /api/v1/admin/subscriptions/{id}/reject` — reject a pending subscription
- `GET /api/v1/admin/errors` — system error log (filterable by status)
- `PATCH /api/v1/admin/errors/{id}/resolve` — mark an error as resolved

**User-facing routes** — require regular auth

- `POST /api/v1/subscriptions/pending` — user submits a bank transfer for review

**Public routes**

- `POST /api/v1/errors/report` — FE reports client-side or API errors (rate-limited)

---

## 2) Contracts

### GET /api/v1/admin/stats

**Auth:** Admin JWT

**Response:**
```json
{
  "total_users": 142,
  "active_users": 38,
  "monthly_revenue_vnd": 1990000,
  "unresolved_errors": 3
}
```

- `active_users` — users whose `last_active_at` falls within the current calendar month
- `monthly_revenue_vnd` — sum of `amount_vnd` where `status='active' AND expires_at > now AND granted_at >= start of current month`
- Format revenue on FE: `${n / 1_000_000}M VND`

---

### GET /api/v1/admin/users

**Auth:** Admin JWT

**Query params:**
| Param | Type | Default | Note |
|-------|------|---------|------|
| `page` | int | `1` | ≥ 1 |
| `limit` | int | `20` | 1–100 |
| `search` | string | — | Case-insensitive substring match on `username` OR `display_name`, max 100 chars |

**Response:**
```json
{
  "items": [
    {
      "id": 12,
      "username": "nguyen_van_a",
      "displayName": "Nguyễn Văn A",
      "accountType": "email",
      "subscriptionStatus": "Pro",
      "subscriptionExpiry": "2026-09-01T00:00:00Z",
      "joinDate": "2026-01-15T08:23:00Z",
      "lastActiveAt": "2026-06-07T14:00:00Z"
    }
  ],
  "total": 142,
  "page": 1,
  "limit": 20
}
```

- `accountType`: `"email"` | `"username"` | `"google"`
- `subscriptionStatus`: `"Pro"` | `"Expired"` | `"None"`
- `subscriptionExpiry`: ISO string or `null` — format as `DD/MM/YYYY` on FE
- `joinDate` / `lastActiveAt`: ISO strings — format as `DD/MM/YYYY` on FE

---

### GET /api/v1/admin/subscriptions/pending

**Auth:** Admin JWT

**Response:** array of pending rows, ordered by `created_at` desc

```json
[
  {
    "id": "uuid",
    "username": "nguyen_van_a",
    "displayName": "Nguyễn Văn A",
    "plan": "Pro 1 tháng",
    "duration": 1,
    "amount": "199,000đ",
    "amount_vnd": 199000,
    "transferDate": "2026-06-07T10:00:00Z",
    "note": "Chuyển khoản VCB"
  }
]
```

- `amount` — display string formatted by BE, e.g. `"199,000đ"`. Use directly in the UI.
- `amount_vnd` — raw integer if you need to sort or compute.

---

### GET /api/v1/admin/subscriptions/active

**Auth:** Admin JWT

**Response:** array of active rows, ordered by `granted_at` desc

```json
[
  {
    "id": "uuid",
    "username": "nguyen_van_a",
    "displayName": "Nguyễn Văn A",
    "plan": "Pro 1 tháng",
    "grantedAt": "2026-06-01T09:00:00Z",
    "expiresAt": "2026-07-01T09:00:00Z"
  }
]
```

---

### POST /api/v1/admin/subscriptions/{id}/grant

**Auth:** Admin JWT

**Route param:** `id` — UUID of the subscription

**Body (optional):**
```json
{ "duration_months": 3 }
```

- If `duration_months` is omitted, uses the value the user submitted. Must be ≥ 1 if provided.
- Only works on `status='pending'` rows — returns `409` otherwise.

**Response:** `SubscriptionActiveRow` (same shape as active list item)

---

### POST /api/v1/admin/subscriptions/{id}/reject

**Auth:** Admin JWT

**Route param:** `id` — UUID of the subscription

**Body:** none

- Only works on `status='pending'` rows — returns `409` otherwise.

**Response:** `SubscriptionPendingRow` (same shape as pending list item, now with `status='rejected'`)

---

### GET /api/v1/admin/errors

**Auth:** Admin JWT

**Query params:**
| Param | Type | Default | Note |
|-------|------|---------|------|
| `status` | `"open"` \| `"resolved"` | — (all) | Filter by resolution status |

**Response:** array ordered by `timestamp` desc

```json
[
  {
    "id": "uuid",
    "timestamp": "2026-06-08T10:30:00Z",
    "type": "HTTP 500",
    "route": "/api/v1/dashboard",
    "severity": "HIGH",
    "status": "open",
    "description": "Internal server error"
  }
]
```

- `severity`: `"HIGH"` | `"MEDIUM"` | `"LOW"`
- `status`: `"open"` | `"resolved"`
- Format `timestamp` as `DD/MM/YYYY HH:mm` on FE

---

### PATCH /api/v1/admin/errors/{id}/resolve

**Auth:** Admin JWT

**Route param:** `id` — UUID of the error

**Body:** none

**Response:** updated `AdminErrorRow` with `status: "resolved"` — idempotent (calling twice is safe)

---

### POST /api/v1/subscriptions/pending

**Auth:** Any authenticated user (regular JWT)

**Body:**
```json
{
  "plan_name": "Pro 1 tháng",
  "duration_months": 1,
  "amount_vnd": 199000,
  "transfer_date": "2026-06-08T09:00:00Z",
  "transfer_note": "Chuyển khoản MB Bank"
}
```

Validation:
- `duration_months`: int, 1–24
- `amount_vnd`: int, ≥ 1
- `transfer_date`: ISO datetime

**Response `201`:**
```json
{ "id": "uuid" }
```

---

### POST /api/v1/errors/report

**Auth:** None (public endpoint)

**Rate limit:** 10 requests / IP / minute → `429 Too Many Requests`

**Body:**
```json
{
  "error_type": "HTTP 500",
  "route": "/api/v1/mood",
  "severity": "HIGH",
  "description": "Network Error: Request failed with status code 500"
}
```

Validation:
- `error_type`: max 100 chars
- `route`: max 500 chars, must start with `/`
- `severity`: `"HIGH"` | `"MEDIUM"` | `"LOW"` (default `"HIGH"`)
- `description`: max 2000 chars

**Response `201`:**
```json
{ "id": "uuid" }
```

---

## 3) Error codes

| HTTP | Trigger |
|------|---------|
| `401` | Missing or invalid/expired JWT |
| `403` | Valid JWT but user not in `ADMIN_USERS` whitelist |
| `404` | Subscription or error ID not found |
| `409` | Duplicate pending subscription (user already has one pending) |
| `409` | Grant/reject on non-pending subscription |
| `422` | Validation failure (missing required field, out-of-range value) |
| `429` | Rate limit exceeded on `POST /errors/report` |

---

## 4) FE notes

**Admin auth flow:**
- 401 fires the existing `lib/api/core.ts` 401-interceptor (session expired → redirect to login) — no change needed in the interceptor.
- 403 means the logged-in user is not an admin. Show a "Không có quyền truy cập" screen rather than redirecting to login.

**Dashboard page (`admin/dashboard/page.tsx`):**
1. Fetch `GET /admin/stats` → fill the 4 stat cards.
2. Fetch `GET /admin/subscriptions/pending` → show first 3 items in the sidebar preview.

**Users page (`admin/users/page.tsx`):**
- Debounce the search input before sending `?search=`.
- `subscriptionStatus` maps to the existing badge keys: `"Pro"` → green, `"Expired"` → orange, `"None"` → grey.

**Subscriptions page (`admin/subscriptions/page.tsx`):**
- Call grant/reject, then re-fetch both `/pending` and `/active` lists.
- Confirm modal stays unchanged — only the submit handler changes.

**Errors page (`admin/errors/page.tsx`):**
- Pass `?status=open|resolved` to the backend when switching filter tabs (preferred over client-side filter).
- `PATCH …/resolve` returns the updated row — update the list in-place rather than re-fetching.

**Error reporting wiring (3 points):**
1. `lib/api/core.ts` — fire-and-forget `POST /errors/report` in the non-401 error handler: severity `"HIGH"` for 5xx, `"MEDIUM"` for other 4xx.
2. `app/layout.tsx` — render `<ClientErrorReporter />` once at root to wire `window.onerror` + `unhandledrejection`.
3. `ClientErrorReporter.tsx` — `"use client"` component with `useEffect` that registers and cleans up the global listeners.

**Revenue display:** `monthly_revenue_vnd` is a raw integer (VND). Format as `{n / 1_000_000}M` for the dashboard card.
