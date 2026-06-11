# BE Handoff: Sounds — Audio Streaming

> Date: 2026-06-11
> Feature: `/services/sounds`

---

## 1) Architecture decision

Audio files **không đi qua FastAPI**. FastAPI chỉ trả metadata.
Files được serve trực tiếp bởi **Nginx** từ Docker volume — không có Python overhead, hỗ trợ `Range` request native (browser seek được ngay).

```
Browser  ──GET /api/v1/sounds──►  FastAPI  ──► PostgreSQL (metadata)
         ──GET /media/sounds/stream.mp3──►  Nginx  ──► Docker volume
```

---

## 2) Database schema

```sql
CREATE TABLE sounds (
  id               VARCHAR(64) PRIMARY KEY,          -- slug, vd: "stream", "rain-light"
  title            VARCHAR(255) NOT NULL,
  description      TEXT,
  category         VARCHAR(64) NOT NULL,             -- xem enum bên dưới
  filename         VARCHAR(255) NOT NULL UNIQUE,     -- tên file trên disk, vd: "stream.mp3"
  duration_seconds INTEGER,                          -- NULL = looping / vô tận
  sort_order       INTEGER NOT NULL DEFAULT 0,       -- thứ tự hiển thị
  is_published     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Enum category
-- 'nature'     → Thiên nhiên
-- 'meditation' → Thiền
-- 'music'      → Nhạc thiền
-- 'noise'      → Tiếng ồn
```

### Seed data (khớp với mock FE)

```sql
INSERT INTO sounds (id, title, description, category, filename, duration_seconds, sort_order) VALUES
  ('stream',          'Tiếng suối chảy',         'Âm thanh trong trẻo của dòng suối nhỏ chảy qua rừng núi.',          'nature',     'stream.mp3',          NULL, 1),
  ('rain-light',      'Tiếng mưa nhẹ',            'Giọt mưa rơi trên mái nhà, xua tan lo lắng.',                       'nature',     'rain-light.mp3',      NULL, 2),
  ('ocean-waves',     'Sóng biển',                'Nhịp điệu đều đặn của sóng biển.',                                  'nature',     'ocean-waves.mp3',     NULL, 3),
  ('forest',          'Tiếng rừng sâu',           'Tiếng chim hót, lá rơi trong không gian rừng nguyên sinh.',         'nature',     'forest.mp3',          NULL, 4),
  ('tibetan-bowl',    'Chuông Tây Tạng',          'Âm thanh cộng hưởng của chuông đồng giúp tập trung.',               'meditation', 'tibetan-bowl.mp3',    1200, 5),
  ('fire-crackling',  'Tiếng lửa crackling',      'Âm thanh lửa cháy trong lò sưởi, ấm áp và thư giãn.',              'meditation', 'fire-crackling.mp3',  NULL, 6),
  ('healing-432hz',   'Nhạc chữa lành 432Hz',     'Âm nhạc ở tần số 432Hz hài hòa với nhịp điệu tự nhiên.',           'music',      'healing-432hz.mp3',   1800, 7),
  ('binaural-alpha',  'Binaural Beats — Alpha',   'Sóng não Alpha (8–12Hz) tạo trạng thái thư giãn tỉnh táo.',         'music',      'binaural-alpha.mp3',  1500, 8),
  ('binaural-theta',  'Binaural Beats — Theta',   'Sóng Theta (4–8Hz) kích thích thiền sâu và cải thiện giấc ngủ.',   'music',      'binaural-theta.mp3',  1800, 9),
  ('white-noise',     'Tiếng ồn trắng',           'White noise che lấp tiếng ồn xung quanh.',                          'noise',      'white-noise.mp3',     NULL, 10),
  ('brown-noise',     'Tiếng ồn nâu',             'Tần số thấp hơn white noise, giống tiếng thác nước.',              'noise',      'brown-noise.mp3',     NULL, 11),
  ('pink-noise',      'Tiếng ồn hồng',            'Cân bằng giữa white và brown noise, cải thiện slow-wave sleep.',   'noise',      'pink-noise.mp3',      NULL, 12);
```

---

## 3) File storage — Docker volume

```yaml
# docker-compose.yml (thêm vào service backend / nginx)
volumes:
  - ./media/sounds:/app/media/sounds:ro   # read-only với app
```

Cấu trúc thư mục trên server:
```
/app/media/sounds/
  stream.mp3
  rain-light.mp3
  ocean-waves.mp3
  ...
```

> Bạn copy file từ "Tài nguyên WEB - Vết Lành/Audio" vào đây là xong.
> Tên file phải khớp với cột `filename` trong DB.

---

## 4) Nginx config — serve file trực tiếp

```nginx
# nginx.conf
location /media/sounds/ {
    alias /app/media/sounds/;

    # Bắt buộc để browser seek được audio
    add_header Accept-Ranges bytes;
    add_header Cache-Control "public, max-age=86400";
    add_header Access-Control-Allow-Origin "$http_origin" always;

    # MIME type
    types {
        audio/mpeg  mp3;
        audio/ogg   ogg;
        audio/wav   wav;
    }
}
```

File URL khi deploy: `https://api.vetlanh.app/media/sounds/stream.mp3`
Local dev: `http://localhost:8000/media/sounds/stream.mp3`

---

## 5) API endpoints

### List sounds

`GET /api/v1/sounds`

**Auth:** Không cần (public)

**Query params:**

| Param | Type | Default | Mô tả |
|-------|------|---------|-------|
| `category` | string | — | Filter: `nature` `meditation` `music` `noise` |

**Response:**
```json
[
  {
    "id": "stream",
    "title": "Tiếng suối chảy",
    "description": "Âm thanh trong trẻo của dòng suối nhỏ chảy qua rừng núi.",
    "category": "nature",
    "duration_seconds": null,
    "sort_order": 1,
    "audio_url": "http://localhost:8000/media/sounds/stream.mp3"
  }
]
```

> `audio_url` được build từ `settings.MEDIA_BASE_URL + "/sounds/" + filename`.
> FE dùng trực tiếp `audio_url` này làm `src` của thẻ `<audio>`.

---

### Get single sound

`GET /api/v1/sounds/{id}`

**Response:** Cùng schema như item trong list.

**Errors:**

| HTTP | Trường hợp |
|------|-----------|
| 404  | `id` không tồn tại hoặc `is_published = false` |

---

## 6) Settings (FastAPI)

```python
# settings.py
MEDIA_BASE_URL: str = "http://localhost:8000"   # production: https://api.vetlanh.app
SOUNDS_DIR: str = "/app/media/sounds"
```

---

## 7) FE notes

**`audio_url` là tất cả những gì FE cần:**

```tsx
// Khi user bấm play:
const audio = new Audio(sound.audio_url);
audio.play();

// Hoặc dùng <audio> tag:
<audio src={sound.audio_url} controls preload="none" />
```

- `preload="none"` — không tải file cho đến khi user bấm play → trang load nhanh
- Nginx đã hỗ trợ `Range` request → browser tự seek không cần code thêm
- `duration_seconds: null` = looping sound → FE set `audio.loop = true`

**Category mapping (FE → BE):**

| FE label | BE value |
|----------|---------|
| Thiên nhiên | `nature` |
| Thiền | `meditation` |
| Nhạc thiền | `music` |
| Tiếng ồn | `noise` |

---

## 8) Error codes

| HTTP | Trường hợp |
|------|-----------|
| 404 | Sound không tồn tại / chưa publish |
| 206 | Range request thành công (Nginx tự xử lý) |
| 416 | Range không hợp lệ (Nginx tự xử lý) |
