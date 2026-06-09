# FE Handoff: Email Verification Flow

> Branch: `dev`
> Date: 2026-06-08

## 1) Endpoint map

- `GET /api/v1/auth/verify` — xác minh email từ link trong mail (no auth)
- `POST /api/v1/auth/resend-verification` — gửi lại email xác minh (no auth)

---

## 2) Contracts

### GET /api/v1/auth/verify

`GET /api/v1/auth/verify?token={token}`

**Auth:** không cần

**Query params:**

| Param | Type | Required | Note |
|-------|------|----------|------|
| `token` | string | ✅ | Lấy từ URL trong email, đã được URL-encode sẵn |

**Response khi thành công (`200`):**
```json
{ "message": "Email verified successfully. You can now log in." }
```

**Response khi đã verify rồi (`200`):**
- Backend trả `200` (idempotent — không lỗi), cùng message trên.

---

### POST /api/v1/auth/resend-verification

`POST /api/v1/auth/resend-verification`

**Auth:** không cần

**Body:**
```json
{ "email": "user@example.com" }
```

**Response (`200`) — luôn trả cùng message dù email tồn tại hay không:**
```json
{ "message": "If that email is registered and unverified, a new link has been sent." }
```

---

## 3) Error codes

| HTTP | Trường hợp | `detail` |
|------|-----------|---------|
| 400 | Token không hợp lệ / không tìm thấy | `"Invalid verification link"` |
| 400 | Token đã hết hạn (24h) | `"Verification link has expired. Please request a new one."` |
| 400 | Resend nhưng email đã verified | `"Email is already verified"` |
| 403 | Login khi chưa verify | `"Please verify your email before logging in"` |
| 422 | Email sai format | FastAPI validation error |

---

## 4) FE notes

### Trang `/verify-email` (nhận token từ link email)

Flow khi user click link trong email:
```
https://vetlanh.io.vn/verify-email?token=abc123
```

1. FE đọc `?token` từ URL → gọi `GET /api/v1/auth/verify?token=abc123`
2. Nếu `200` → hiện thông báo thành công + nút "Đăng nhập ngay" → redirect `/login`
3. Nếu `400` với `"expired"` → hiện nút "Gửi lại email xác minh"
4. Nếu `400` với `"Invalid"` → hiện thông báo "Link không hợp lệ"

> **Lưu ý:** Không cần user nhập gì — toàn bộ flow là one-click từ email.

### Trang resend / sau khi đăng ký

- Khi `POST /auth/register` thành công (`201`) → `is_verified: false` → FE nên hiện màn hình "Kiểm tra email của bạn" thay vì redirect thẳng vào app.
- Nếu user login khi chưa verify → nhận `403` với `"Please verify your email"` → hiện nút **"Gửi lại email xác minh"** dẫn đến form resend.
- Form resend chỉ cần 1 field `email` → gọi `POST /api/v1/auth/resend-verification` → luôn hiện message thành công (backend không tiết lộ email có tồn tại hay không).

### Suggested call order

```
POST /auth/register
  └─ 201 → show "Kiểm tra email" screen
       └─ user click link → GET /auth/verify?token=...
            ├─ 200 → redirect /login
            └─ 400 expired → show resend form → POST /auth/resend-verification
```
