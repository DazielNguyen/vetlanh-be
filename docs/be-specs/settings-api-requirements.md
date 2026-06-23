# BE API Requirements — Settings Page

**Date:** 2026-06-22  
**Requested by:** FE Team  
**Priority:** Medium  
**Context:** Settings page at `/services/settings` currently has stub UI for personal info, security, and avatar upload. FE is ready to wire these up once BE endpoints are available.

---

## Existing Endpoints (already available)

| Method | Endpoint | Used for |
|--------|----------|----------|
| `PATCH` | `api/v1/users/me` | Update `display_name`, `avatar_url` (URL string), `timezone` |
| `GET` | `api/v1/users/me` | Fetch current user profile |

The FE `UpdateProfileRequest` type currently accepts:
```typescript
{
  display_name?: string;
  avatar_url?: string;   // URL string, not file
  timezone?: string;
}
```

---

## New Endpoints Required

### 1. Change Password

**Endpoint:** `POST api/v1/auth/change-password`  
**Auth:** Required (Bearer token)

**Request body:**
```json
{
  "current_password": "string",
  "new_password": "string"
}
```

**Response (200 OK):**
```json
{
  "message": "Mật khẩu đã được cập nhật thành công."
}
```

**Error cases:**
- `400` — `current_password` incorrect → `{ "detail": "Mật khẩu hiện tại không đúng." }`
- `400` — `new_password` same as current → `{ "detail": "Mật khẩu mới không được trùng với mật khẩu hiện tại." }`
- `400` — `new_password` too short (< 8 chars) → `{ "detail": "Mật khẩu phải có ít nhất 8 ký tự." }`
- `401` — Unauthorized

**FE notes:**
- FE will show a form with 3 fields: current password, new password, confirm new password
- Confirm field is validated client-side only (not sent to BE)
- No logout required after password change (keep current session active)

---

### 2. Change Email

**Endpoint:** `PATCH api/v1/users/me/email`  
**Auth:** Required (Bearer token)

**Request body:**
```json
{
  "new_email": "string",
  "current_password": "string"
}
```

**Response (200 OK):**
```json
{
  "message": "Email xác thực đã được gửi đến địa chỉ mới của bạn."
}
```

**Expected flow:**
1. User submits new email + current password
2. BE validates password, sends verification email to `new_email`
3. FE redirects user to `/verify-pending?email={new_email}`
4. User clicks link in email → BE updates `email` field on user record + sets `is_verified: true`
5. On next `GET api/v1/users/me`, FE receives updated email

**Error cases:**
- `400` — `current_password` incorrect → `{ "detail": "Mật khẩu không đúng." }`
- `400` — `new_email` already registered → `{ "detail": "Email này đã được sử dụng bởi tài khoản khác." }`
- `400` — `new_email` same as current → `{ "detail": "Email mới không được trùng với email hiện tại." }`
- `401` — Unauthorized

**FE notes:**
- The existing `api/v1/auth/verify` endpoint (used for initial registration verify) should also work for email-change verification — confirm with BE team
- If a separate verify endpoint is needed for email change, FE needs to know the token param name

---

### 3. Upload Avatar

**Endpoint:** `POST api/v1/users/me/avatar`  
**Auth:** Required (Bearer token)  
**Content-Type:** `multipart/form-data`

**Request:**
```
Form field: "file" — image file (jpg, png, webp)
Max size: 5MB
```

**Response (200 OK):**
```json
{
  "avatar_url": "https://cdn.example.com/avatars/user-123.jpg"
}
```

**Expected flow:**
1. FE uploads file → BE stores it (S3/CDN/local) and returns public URL
2. FE calls `PATCH api/v1/users/me` with `{ avatar_url: "<returned URL>" }` to persist
3. React Query invalidates `["user", "me"]` cache → ProfileCard re-renders with new avatar

**Error cases:**
- `400` — file not an image → `{ "detail": "Chỉ chấp nhận file ảnh (jpg, png, webp)." }`
- `413` — file too large → `{ "detail": "Kích thước file không được vượt quá 5MB." }`
- `401` — Unauthorized

**FE notes:**
- FE will handle image preview before upload (FileReader API, client-side only)
- FE will show upload progress indicator
- No separate `avatar_url` update call needed if BE returns `avatar_url` AND updates the user record atomically — confirm behavior

---

## Summary Table

| Endpoint | Method | Priority | Complexity |
|----------|--------|----------|------------|
| `api/v1/auth/change-password` | POST | High | Low |
| `api/v1/users/me/email` | PATCH | Medium | Medium (verify flow) |
| `api/v1/users/me/avatar` | POST | Medium | Medium (file storage) |

**Recommended implementation order:** change-password first (no side effects), then avatar upload, then email change (most complex due to re-verify flow).

---

## Questions for BE Team

1. For email change: does the existing `api/v1/auth/verify?token=...` endpoint work for verifying a new email address, or does it need to be a separate endpoint?
2. For avatar upload: will BE update `avatar_url` on the user record automatically, or does FE need to call `PATCH api/v1/users/me` separately after upload?
3. Is there a rate limit on `api/v1/auth/change-password` to prevent brute-force?
