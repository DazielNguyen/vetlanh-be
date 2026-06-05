# FE Handoff: AI Chatbot — Bạn Đồng Hành (Epic E2)

> Branch: `dev`
> Date: 2026-06-05
> Epic: E2 — US-006 (streaming chat), US-007 (CBT), US-008 (sentiment), US-009 (exercise cards)

---

## 1) Endpoint map

- `POST /api/v1/chat/conversations` — Tạo conversation mới
- `GET /api/v1/chat/conversations` — Lấy danh sách conversations của user (có tìm kiếm)
- `DELETE /api/v1/chat/conversations/{id}` — Xoá conversation
- `GET /api/v1/chat/conversations/{id}/messages` — Lấy lịch sử tin nhắn
- `POST /api/v1/chat/conversations/{id}/messages` — Gửi tin nhắn → nhận SSE stream từ AI

---

## 2) Contracts

### POST /api/v1/chat/conversations

**Auth:** JWT Bearer (any authenticated user)

**Body:**
```json
{ "title": "Hôm nay tôi buồn" }
```

| Field | Type | Required | Note |
|-------|------|----------|------|
| `title` | string \| null | No | Nếu null, backend sẽ không tự generate — để null nếu muốn bỏ trống |

**Response `201`:**
```json
{
  "id": 1,
  "title": "Hôm nay tôi buồn",
  "created_at": "2026-06-05T10:00:00Z",
  "updated_at": "2026-06-05T10:00:00Z"
}
```

---

### GET /api/v1/chat/conversations

**Auth:** JWT Bearer

**Query params:**
| Param | Type | Default | Note |
|-------|------|---------|------|
| `q` | string | — | Tìm kiếm theo nội dung, min 1 ký tự, max 200 |

**Response `200`** — array of:
```json
[
  {
    "id": 1,
    "title": "Hôm nay tôi buồn",
    "message_count": 12,
    "last_message_preview": "Cảm ơn bạn đã chia sẻ...",
    "last_message_at": "2026-06-05T10:30:00Z",
    "created_at": "2026-06-05T10:00:00Z",
    "updated_at": "2026-06-05T10:30:00Z"
  }
]
```

---

### DELETE /api/v1/chat/conversations/{id}

**Auth:** JWT Bearer (chỉ owner mới xoá được)

**Response `204`:** No content

---

### GET /api/v1/chat/conversations/{id}/messages

**Auth:** JWT Bearer (chỉ owner mới xem được)

**Response `200`** — array of, sắp xếp theo `created_at` tăng dần:
```json
[
  {
    "id": 10,
    "role": "user",
    "content": "Hôm nay tôi rất căng thẳng",
    "sentiment": "negative",
    "created_at": "2026-06-05T10:05:00Z"
  },
  {
    "id": 11,
    "role": "assistant",
    "content": "Nghe có vẻ bạn đang trải qua giai đoạn khó khăn...",
    "sentiment": null,
    "created_at": "2026-06-05T10:05:05Z"
  }
]
```

| Field | Type | Note |
|-------|------|------|
| `role` | `"user"` \| `"assistant"` | Dùng để phân biệt bong bóng chat trái/phải |
| `sentiment` | `"positive"` \| `"neutral"` \| `"negative"` \| null | Chỉ có ở `role=user`; assistant message luôn null |

---

### POST /api/v1/chat/conversations/{id}/messages — SSE Stream

**Auth:** JWT Bearer

**Content-Type request:** `application/json`

**Body:**
```json
{ "content": "Tôi đang rất lo lắng..." }
```

| Field | Type | Required | Constraint |
|-------|------|----------|------------|
| `content` | string | Yes | min 1, max 4000 ký tự |

**Response:** `text/event-stream` — Server-Sent Events

#### SSE Event Types

**1. chunk** — token AI stream (nhận liên tục):
```
data: {"type": "chunk", "content": "Xin chào"}

data: {"type": "chunk", "content": " bạn"}
```

**2. done** — kết thúc stream (nhận 1 lần duy nhất):
```
data: {
  "type": "done",
  "message_id": 42,
  "exercise_card": {
    "id": "box-breathing",
    "title": "Hít thở hộp",
    "description": "Kỹ thuật giúp hệ thần kinh bình tĩnh trong 4 phút",
    "steps": [
      {"order": 1, "instruction": "Hít vào", "duration_seconds": 4},
      {"order": 2, "instruction": "Nín thở", "duration_seconds": 4},
      {"order": 3, "instruction": "Thở ra", "duration_seconds": 4},
      {"order": 4, "instruction": "Nín thở", "duration_seconds": 4}
    ]
  },
  "sentiment": "negative",
  "suggest_checkin": false
}
```

| Field | Type | Note |
|-------|------|------|
| `message_id` | int | ID của assistant message vừa lưu DB |
| `exercise_card` | object \| null | Non-null khi AI đề xuất bài tập thở/thiền |
| `sentiment` | `"positive"` \| `"neutral"` \| `"negative"` | Sentiment của user message |
| `suggest_checkin` | boolean | `true` khi 5 tin nhắn liên tiếp đều negative — hiện banner nhẹ nhàng gợi ý check-in |

**3. error** — lỗi xảy ra trong stream (message không được lưu):
```
data: {"type": "error", "detail": "AI service unavailable"}
```

---

## 3) Error codes

| HTTP | Trường hợp |
|------|-----------|
| 401 | Thiếu hoặc sai JWT token |
| 403 | User không phải owner của conversation |
| 404 | `detail: "Conversation not found"` |
| 422 | Validation lỗi (content trống, quá 4000 ký tự, q quá ngắn/dài) |

---

## 4) FE notes

**SSE setup:**
- Request header phải có `Authorization: Bearer <token>` — SSE không tự gửi cookie.
- Dùng `EventSource` không hỗ trợ POST và custom headers. Dùng `fetch` + `ReadableStream` hoặc thư viện như `@microsoft/fetch-event-source`.
- Headers bắt buộc khi nhận SSE: backend trả `Cache-Control: no-cache` và `X-Accel-Buffering: no` — không cần set phía FE.

**Render flow gợi ý:**
1. User gửi → tạo message bubble `role=user` ngay (optimistic UI).
2. Nhận `chunk` → append vào bubble `role=assistant` (streaming effect).
3. Nhận `done` → lưu `message_id`; nếu `exercise_card != null`, hiện inline card bên dưới bubble AI; nếu `suggest_checkin == true`, hiện soft banner "Bạn có muốn kiểm tra tâm trạng hôm nay không?" (không popup).
4. Nhận `error` → xoá bubble AI, hiện toast.

**exercise_card hiện tại có 2 loại** (dựa trên trigger keyword trong câu AI):
- `box-breathing` — lo lắng/hồi hộp
- `4-7-8-breathing` — căng thẳng/mất ngủ

**sentiment** của user message được phân tích sau khi stream xong (không block stream), nên khi load lại lịch sử qua `GET /messages`, `sentiment` đã có giá trị.

**Lưu ý bảo mật:** User chỉ truy cập được conversation của chính họ. Backend trả 403 nếu `conversation.user_id != current_user.id`.
