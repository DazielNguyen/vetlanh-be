# FE Handoff: Journal (Nhật Ký Cá Nhân)

> Branch: `dev`
> Date: 2026-06-06

## 1) Endpoint map

- `POST /api/v1/journal` — tạo entry mới (HTTP 201)
- `GET /api/v1/journal` — danh sách entries, phân trang, tìm kiếm theo keyword
- `GET /api/v1/journal/{id}` — lấy một entry cụ thể
- `PATCH /api/v1/journal/{id}` — cập nhật title và/hoặc content (hỗ trợ auto-save)
- `DELETE /api/v1/journal/{id}` — xoá entry (HTTP 204)

> **Note (Sprint 4):** `GET /api/v1/journal?q=` hiện chỉ tìm theo **title**. Search theo content đã bị tắt sau khi bật mã hoá at-rest (see Sprint 4 handoff).

---

## 2) Contracts

### POST /api/v1/journal

`POST /api/v1/journal`

**Auth:** any authenticated user (Bearer JWT)

**Body:**
```json
{
  "title": "Ngày đầu tiên",
  "content": "Hôm nay tôi cảm thấy..."
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `title` | string \| null | no | max 200 chars |
| `content` | string | no | default `""`, max 10,000 chars |

**Response (201):**
```json
{
  "id": 42,
  "title": "Ngày đầu tiên",
  "content": "Hôm nay tôi cảm thấy...",
  "word_count": 4,
  "created_at": "2026-06-06T08:00:00Z",
  "updated_at": "2026-06-06T08:00:00Z"
}
```

- `word_count` được tính server-side từ `content`, lưu vào DB — không cần tính ở FE.

---

### GET /api/v1/journal

`GET /api/v1/journal`

**Auth:** any authenticated user

**Query params:**
| Param | Type | Default | Constraints |
|-------|------|---------|-------------|
| `q` | string \| null | — | Tìm theo title (max 200 chars). Không phân biệt hoa thường |
| `limit` | integer | 20 | 1–100 |
| `offset` | integer | 0 | ≥ 0 |

**Response (200):**
```json
[
  {
    "id": 42,
    "title": "Ngày đầu tiên",
    "content": "Hôm nay tôi cảm thấy...",
    "word_count": 4,
    "created_at": "2026-06-06T08:00:00Z",
    "updated_at": "2026-06-06T08:00:00Z"
  }
]
```

- Kết quả sắp xếp mới nhất trước (`ORDER BY created_at DESC`).
- Response là array thuần, không có wrapper object hay `total` count — implement infinite scroll bằng cách tăng `offset` cho đến khi array trả về ít hơn `limit`.

---

### GET /api/v1/journal/{id}

`GET /api/v1/journal/{id}`

**Auth:** any authenticated user

**Route param:** `id` — integer, ID của entry.

**Response (200):** cùng shape với từng phần tử trong list.

---

### PATCH /api/v1/journal/{id}

`PATCH /api/v1/journal/{id}`

**Auth:** any authenticated user

**Body (ít nhất 1 field bắt buộc):**
```json
{
  "title": "Tiêu đề mới",
  "content": "Nội dung mới..."
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `title` | string \| null | no | max 200 chars |
| `content` | string \| null | no | max 10,000 chars |

Validation rules:
- Phải gửi ít nhất 1 trong 2 field. Body rỗng `{}` → HTTP 422.
- Đây là **partial update** — chỉ field nào được gửi mới được cập nhật. Gửi `{"content": "..."}` mà không gửi `title` → title giữ nguyên.

**Response (200):** entry sau khi cập nhật, `word_count` được tính lại từ `content` mới.

---

### DELETE /api/v1/journal/{id}

`DELETE /api/v1/journal/{id}`

**Auth:** any authenticated user

**Response (204):** no body.

---

## 3) Error codes

| HTTP | message | When |
|------|---------|------|
| 401 | — | Missing hoặc expired JWT |
| 404 | `"Journal entry not found"` | `id` không tồn tại hoặc thuộc về user khác |
| 422 | — | PATCH body rỗng `{}`; field vượt max_length; `limit`/`offset` ngoài range |

---

## 4) FE notes

- **Auto-save:** PATCH hỗ trợ gửi riêng `content` hoặc `title` — dùng cho auto-save sau mỗi N giây. Debounce ít nhất 1–2s trước khi gọi để tránh spam request.
- **Pagination:** API không trả `total`. Implement "load more" bằng cách tăng `offset += limit`. Khi mảng trả về có độ dài < `limit` thì đã hết dữ liệu.
- **Search:** `q=` tìm **title only** (case-insensitive). Cập nhật placeholder UI từ "Tìm kiếm..." thành "Tìm theo tiêu đề..." để tránh user nhầm.
- **word_count:** dùng trực tiếp từ response để hiển thị ("X từ") — không cần đếm lại ở FE.
- **title optional:** `title` có thể là `null` — hiển thị fallback như "Untitled" hoặc dùng ngày tạo làm tiêu đề thay thế.
- **Ownership:** backend tự scope theo user từ JWT — FE không cần gửi `user_id`. Mọi entry trả về đều thuộc về user đang đăng nhập.
