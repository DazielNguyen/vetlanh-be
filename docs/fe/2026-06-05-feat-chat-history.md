# FE Handoff: Lịch Sử Hội Thoại (Epic E2 — US-010)

> Branch: `dev`
> Date: 2026-06-05
> Epic: E2 (cont.) — US-010: danh sách phiên chat theo ngày, tìm kiếm nội dung, xoá phiên chat

---

## 1) Endpoint map

- `GET /api/v1/chat/conversations` — Lấy danh sách conversations (có preview + tìm kiếm)
- `DELETE /api/v1/chat/conversations/{id}` — Xoá conversation và toàn bộ tin nhắn bên trong

> **Lưu ý:** Đây là phần mở rộng của Epic E2 AI Chatbot. Các endpoint `POST /conversations`, `GET /conversations/{id}/messages`, `POST /conversations/{id}/messages` đã có trong [2026-06-05-feat-ai-chatbot.md](2026-06-05-feat-ai-chatbot.md).

---

## 2) Contracts

### GET /api/v1/chat/conversations

`GET /api/v1/chat/conversations`

**Auth:** JWT Bearer (any authenticated user)

**Query params:**
| Param | Type | Default | Note |
|-------|------|---------|------|
| `q` | string \| null | — | Tìm kiếm theo title hoặc nội dung tin nhắn; min 1, max 200 ký tự |

**Response `200`** — array, sắp xếp theo `last_message_at` DESC (conversation mới nhất lên đầu):
```json
[
  {
    "id": 1,
    "title": "Hôm nay tôi buồn",
    "message_count": 12,
    "last_message_preview": "Cảm ơn bạn đã chia sẻ, nghe có vẻ bạn đang...",
    "last_message_at": "2026-06-05T10:30:00Z",
    "created_at": "2026-06-05T10:00:00Z",
    "updated_at": "2026-06-05T10:30:00Z"
  }
]
```

| Field | Type | Note |
|-------|------|------|
| `message_count` | int | Tổng số tin nhắn (user + assistant) trong conversation |
| `last_message_preview` | string \| null | 100 ký tự đầu của tin nhắn cuối cùng; null nếu conversation chưa có tin nhắn |
| `last_message_at` | datetime \| null | Thời điểm tin nhắn cuối; null nếu chưa có tin nhắn |

---

### DELETE /api/v1/chat/conversations/{id}

`DELETE /api/v1/chat/conversations/{conversation_id}`

**Auth:** JWT Bearer (chỉ owner mới xoá được)

**Route params:**
| Param | Type | Note |
|-------|------|------|
| `conversation_id` | int | ID của conversation cần xoá |

**Response `204`:** No content — xoá thành công, messages bên trong bị cascade delete tự động.

---

## 3) Error codes

| HTTP | Trường hợp |
|------|-----------|
| 401 | Thiếu hoặc sai JWT token |
| 404 | Conversation không tồn tại hoặc không thuộc user hiện tại |
| 422 | `q` có độ dài < 1 hoặc > 200 ký tự |

> **Quan trọng:** Backend trả `404` (không phải `403`) khi user cố xoá conversation của người khác — để không lộ sự tồn tại của resource.

---

## 4) FE notes

**Search (`?q=`):**
- Backend tìm kiếm ILIKE (case-insensitive) trên cả `title` lẫn nội dung tin nhắn bên trong — không cần gửi request riêng.
- Debounce input search ~300ms trước khi gửi request để tránh spam.
- Khi `q` rỗng, truyền `null` hoặc bỏ param hoàn toàn — không truyền chuỗi rỗng `""` (422).

**Danh sách conversations:**
- Đã sắp xếp `last_message_at DESC` từ backend — không cần sort phía client.
- `last_message_preview` lấy từ tin nhắn cuối (có thể là assistant hoặc user) — dùng để hiển thị preview trong list item.
- Conversation mới tạo chưa gửi tin nhắn sẽ có `message_count: 0`, `last_message_preview: null`, `last_message_at: null`.

**Delete flow:**
- Xoá thành công → `204` không có body → remove item khỏi local list (không cần refetch).
- Nếu nhận `404` khi xoá → conversation đã bị xoá hoặc không còn tồn tại → cũng remove khỏi local list + hiện toast "Hội thoại không còn tồn tại".
- Messages bên trong bị xoá cascade — không cần gọi thêm endpoint nào.
