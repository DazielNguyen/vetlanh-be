# FE Handoff: Sounds API

> Branch: `dev`
> Date: 2026-06-11

## 1) Endpoint map

- `GET /api/v1/sounds` — danh sách sounds đã publish, filter tùy chọn theo category
- `GET /api/v1/sounds/{id}` — chi tiết 1 sound
- `POST /api/v1/sounds` — tạo sound mới _(admin only)_
- `PATCH /api/v1/sounds/{id}` — cập nhật partial _(admin only)_
- `DELETE /api/v1/sounds/{id}` — xóa sound _(admin only)_

---

## 2) Contracts

### GET /api/v1/sounds

**Auth:** Không cần

**Query params:**

| Param | Type | Default | Note |
|-------|------|---------|------|
| `category` | `string` | _(bỏ qua = tất cả)_ | `nature` \| `meditation` \| `music` \| `noise` |

**Response — `SoundResponse[]`:**

```json
[
  {
    "id": "stream",
    "title": "Tiếng suối chảy",
    "description": "Âm thanh trong trẻo của dòng suối",
    "category": "nature",
    "audio_url": "https://res.cloudinary.com/dxml1zqnw/video/upload/sounds/stream.mp3",
    "duration_seconds": null,
    "sort_order": 1
  },
  {
    "id": "healing-432hz",
    "title": "Nhạc chữa lành 432Hz",
    "description": null,
    "category": "music",
    "audio_url": "https://res.cloudinary.com/dxml1zqnw/video/upload/sounds/healing-432hz.mp3",
    "duration_seconds": 1800,
    "sort_order": 7
  }
]
```

---

### GET /api/v1/sounds/{id}

**Auth:** Không cần

**Path param:** `id` — slug của sound (ví dụ: `stream`, `rain-light`)

**Response — `SoundResponse` (object đơn):**

```json
{
  "id": "stream",
  "title": "Tiếng suối chảy",
  "description": "Âm thanh trong trẻo của dòng suối",
  "category": "nature",
  "audio_url": "https://res.cloudinary.com/dxml1zqnw/video/upload/sounds/stream.mp3",
  "duration_seconds": null,
  "sort_order": 1
}
```

---

### POST /api/v1/sounds _(admin)_

**Auth:** Bearer token — tài khoản trong `ADMIN_USERS`

**Body:**

```json
{
  "id": "stream",
  "title": "Tiếng suối chảy",
  "description": "Âm thanh trong trẻo của dòng suối",
  "category": "nature",
  "cloudinary_public_id": "sounds/stream",
  "audio_url": "https://res.cloudinary.com/dxml1zqnw/video/upload/sounds/stream.mp3",
  "duration_seconds": null,
  "sort_order": 1,
  "is_published": true
}
```

| Field | Type | Required | Note |
|-------|------|----------|------|
| `id` | `string` | ✅ | Slug unique, ví dụ `stream` |
| `title` | `string` | ✅ | |
| `description` | `string \| null` | — | Default `null` |
| `category` | `string` | ✅ | `nature` \| `meditation` \| `music` \| `noise` |
| `cloudinary_public_id` | `string` | ✅ | Public ID lấy từ Cloudinary dashboard |
| `audio_url` | `string` | ✅ | URL trực tiếp từ Cloudinary |
| `duration_seconds` | `number \| null` | — | `null` = looping, default `null` |
| `sort_order` | `number` | — | Default `0` |
| `is_published` | `boolean` | — | Default `true` |

**Response:** `SoundResponse` — 201 Created

---

### PATCH /api/v1/sounds/{id} _(admin)_

**Auth:** Bearer token — tài khoản trong `ADMIN_USERS`

**Path param:** `id` — slug của sound

**Body:** tất cả các field đều optional (partial update)

```json
{
  "title": "Tên mới",
  "is_published": false
}
```

| Field | Type | Note |
|-------|------|------|
| `title` | `string` | |
| `description` | `string \| null` | |
| `category` | `string` | |
| `cloudinary_public_id` | `string` | |
| `audio_url` | `string` | |
| `duration_seconds` | `number \| null` | |
| `sort_order` | `number` | |
| `is_published` | `boolean` | Dùng để ẩn/hiện sound mà không cần xóa |

**Response:** `SoundResponse` — 200 OK

---

### DELETE /api/v1/sounds/{id} _(admin)_

**Auth:** Bearer token — tài khoản trong `ADMIN_USERS`

**Path param:** `id` — slug của sound

**Response:** 204 No Content (không có body)

---

## 3) Error codes

| HTTP | message | Endpoint |
|------|---------|---------|
| 404 | `"Sound not found"` | GET `/{id}`, PATCH `/{id}`, DELETE `/{id}` |
| 409 | `"Sound with this id already exists"` | POST |
| 401 | `"Not authenticated"` | POST, PATCH, DELETE — thiếu token |
| 403 | `"Admin access required"` | POST, PATCH, DELETE — token hợp lệ nhưng không phải admin |

---

## 4) FE notes

- **`audio_url` dùng thẳng** — nhét vào `<audio src="...">` là phát được, không cần bước transform.

- **`duration_seconds: null` = looping** — ẩn progress bar, chỉ hiện nút stop/pause.

- **Server đã sort sẵn** theo `sort_order` tăng dần — FE không cần sort lại.

- **Không có pagination** — tập data nhỏ (~12 items), 1 request là xong.

- **Ẩn/hiện sound** — dùng `PATCH /{id}` với `{ "is_published": false }` thay vì xóa. `GET /sounds` chỉ trả về `is_published: true`.

- **Xóa mock data cũ** — `GET /api/v1/resources/recommended` còn item audio mock (`id: "sleep-meditation"`, `url: null`). Thay màn hình ambient sounds bằng `GET /api/v1/sounds`.
