# FE Handoff: Chat — Emotion Analysis & Mood-Based Exercises

> Branch: `dev`
> Date: 2026-06-11
> Commits: `838b3c5` feat(chat) · `d0517dd` feat(emotions)

---

## 1) Endpoint map

- `POST /api/v1/chat/conversations/{id}/messages` — **done event mở rộng** với emotion analysis và exercise cards theo tâm trạng
- `GET /api/v1/chat/quick-prompts` — nội dung 5 prompt mới (cùng cấu trúc, thay nội dung)

---

## 2) Contracts

### Send Message — SSE Stream

`POST /api/v1/chat/conversations/{conversation_id}/messages`

**Auth:** Bearer token (any authenticated user)

**Body:**
```json
{ "content": "Tôi cảm thấy rất mệt mỏi" }
```

| Field | Type | Required | Constraint |
|-------|------|----------|------------|
| `content` | string | ✓ | 1–4000 ký tự |

---

**SSE events:**

#### `chunk` — token stream (không đổi)
```json
{ "type": "chunk", "content": "Mình" }
```

#### `done` — kết thúc stream **(thay đổi)**

```json
{
  "type": "done",
  "message_id": 42,
  "sentiment": "negative",
  "suggest_checkin": false,
  "crisis_level": 0,

  "emotion": "sad",
  "emotion_confidence": 0.68,
  "depression_risk": "mild",
  "phq_estimate": 5.4,

  "exercise_card": {
    "id": "grounding-54321",
    "title": "Grounding 5-4-3-2-1",
    "description": "Kỹ thuật đưa bản thân trở về hiện tại bằng 5 giác quan.",
    "steps": [
      { "order": 1, "instruction": "Nhìn xung quanh — kể 5 thứ bạn nhìn thấy", "duration_seconds": null },
      { "order": 2, "instruction": "Chạm vào đồ vật — kể 4 thứ bạn cảm nhận được", "duration_seconds": null },
      { "order": 3, "instruction": "Lắng nghe — kể 3 âm thanh bạn đang nghe", "duration_seconds": null },
      { "order": 4, "instruction": "Ngửi — kể 2 mùi (hoặc mùi yêu thích)", "duration_seconds": null },
      { "order": 5, "instruction": "Nếm — kể 1 thứ bạn cảm nhận được", "duration_seconds": null }
    ]
  }
}
```

**Các field mới trong `done`:**

| Field | Type | Values | Mô tả |
|-------|------|--------|-------|
| `emotion` | string | `neutral` `happy` `sad` `angry` `anxious` `tired` `disgusted` | Cảm xúc nhận diện từ tin nhắn user |
| `emotion_confidence` | float | 0.0–1.0 | Độ tin cậy — nếu < 0.55 nên hiển thị mờ hoặc ẩn |
| `depression_risk` | string | `none` `mild` `moderate` `severe` | Mức nguy cơ trầm cảm |
| `phq_estimate` | float | 0–27 | PHQ-9 ước tính — **không hiển thị per-message** |

**`exercise_card` — 8 loại bài tập theo tâm trạng (trước chỉ có box-breathing):**

| `id` | Tên | Khi nào xuất hiện |
|------|-----|-------------------|
| `box-breathing` | Thở Hộp (4-4-4-4) | Lo âu, căng thẳng, tức giận |
| `breathing-4-7-8` | Thở 4-7-8 | Mất ngủ |
| `coherent-breathing` | Coherent Breathing | Buồn, thiếu năng lượng |
| `grounding-54321` | Grounding 5-4-3-2-1 | Lo âu, tức giận |
| `meditation-loving-kindness` | Loving-Kindness | Buồn, cô đơn |
| `pmr-7-groups` | Thư Giãn Cơ Tuần Tiến | Tức giận, căng cơ |
| `meditation-body-scan` | Body Scan | Overthinking, căng thẳng |
| `meditation-breath` | Thiền Hơi Thở | Tâm trí bận rộn |

> `steps[].duration_seconds` có thể là `null` (bài tập không có bộ đếm thời gian từng bước, ví dụ Grounding, Loving-Kindness). FE cần xử lý trường hợp null.

#### `error` — lỗi stream (không đổi)
```json
{ "type": "error", "detail": "Không thể kết nối với AI. Vui lòng thử lại." }
```

---

### Quick Prompts

`GET /api/v1/chat/quick-prompts`

**Auth:** Không cần

**Response:**
```json
[
  { "id": "qp-1", "text": "Tôi đang cảm thấy lo lắng và không biết phải làm gì" },
  { "id": "qp-2", "text": "Hôm nay tôi rất buồn và trống rỗng, bạn có thể lắng nghe không?" },
  { "id": "qp-3", "text": "Tôi đang tức giận và cần giải tỏa" },
  { "id": "qp-4", "text": "Tôi bị mất ngủ, giúp tôi thư giãn trước khi ngủ" },
  { "id": "qp-5", "text": "Đầu óc tôi đang rất bận rộn, tôi muốn tập chánh niệm" }
]
```

> Cấu trúc `{id, text}` không đổi — chỉ cập nhật nội dung text.

---

## 3) Error codes

| HTTP | Trường hợp | Message |
|------|-----------|---------|
| 404 | Conversation không tồn tại | `"Conversation not found"` |
| 403 | Conversation thuộc user khác | `"Access denied"` |
| SSE `error` event | Groq timeout / lỗi kết nối | `"Không thể kết nối với AI. Vui lòng thử lại."` |

---

## 4) FE notes

**Hiển thị `emotion`:**
- Hiển thị icon + label nhỏ ngay dưới tin nhắn của user (không phải assistant).
- Ẩn nếu `emotion === "neutral"` hoặc `emotion_confidence < 0.55`.
- Mapping gợi ý: `sad` → 😔, `anxious` → 😰, `angry` → 😤, `tired` → 😩, `happy` → 😊, `disgusted` → 😞.

**`depression_risk` — KHÔNG hiển thị label trực tiếp trong chat:**
- Dùng nội bộ để quyết định UX: nếu `moderate` hoặc `severe` → có thể hiện banner nhẹ "Bạn có muốn nói chuyện với chuyên gia?" (một lần per session).
- `phq_estimate` dành cho màn hình "Sức khỏe tâm thần" / dashboard riêng — không per-message.

**`exercise_card` — `duration_seconds` nullable:**
- Nếu `duration_seconds === null`: hiển thị bước dưới dạng checklist (user tự bấm "Xong"), không chạy bộ đếm giờ.
- Nếu `duration_seconds` là số: chạy countdown timer cho bước đó.

**`suggest_checkin`:**
- Giữ nguyên behavior cũ: khi `true`, hiện prompt mời user làm mood check-in.

**`crisis_level`:**
- `0` = bình thường, `1` = lo âu nhẹ, `2` = nghiêm trọng, `3` = khủng hoảng (stream dừng lại, không có AI response — chỉ có done event với `crisis_level: 3`).
- Level 3: hiện ngay màn hình hotline `1800 599 920` thay vì response text.

**Backward compatibility:**
- `sentiment` (`"positive"|"neutral"|"negative"`) vẫn có trong `done` event — không cần xóa logic cũ.
- Các field emotion mới có thể vắng mặt nếu analysis fail (graceful degrade) — luôn optional-chain khi đọc.
