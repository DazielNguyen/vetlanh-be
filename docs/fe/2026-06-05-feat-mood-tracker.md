# FE Handoff: Theo Dõi Tâm Trạng (Epic E3)

> Branch: `dev`
> Date: 2026-06-05
> Epic: E3 — US-011 (check-in), US-012 (trend chart), US-013 (PHQ-9 history & reminder)

---

## 1) Endpoint map

**Mood:**
- `POST /api/v1/mood/entries` — Tạo hoặc cập nhật check-in tâm trạng (upsert theo ngày)
- `GET /api/v1/mood/entries` — Lấy lịch sử check-in (filter theo date range, paginated)
- `GET /api/v1/mood/trend` — Lấy dữ liệu chart tâm trạng theo tuần hoặc tháng
- `GET /api/v1/mood/heatmap` — Lấy dữ liệu heatmap theo năm/tháng
- `GET /api/v1/mood/insights` — _(xem riêng tại [2026-06-05-feat-insights.md](2026-06-05-feat-insights.md))_

**PHQ-9:**
- `GET /api/v1/assessments/phq9/history` — Lấy toàn bộ lịch sử PHQ-9 (paginated, có score_delta)
- `GET /api/v1/assessments/phq9/reminder` — Kiểm tra user có cần làm lại PHQ-9 không

---

## 2) Contracts

### POST /api/v1/mood/entries

**Auth:** JWT Bearer

**Body:**
```json
{
  "date": "2026-06-05",
  "mood": 4,
  "energy": "medium",
  "factors": ["tập thể dục", "gia đình"],
  "note": "Hôm nay khá ổn"
}
```

| Field | Type | Required | Constraint |
|-------|------|----------|------------|
| `date` | string (ISO date) | Yes | Ngày local của user, format `YYYY-MM-DD` |
| `mood` | int | Yes | 1–5 (1=😔 2=😟 3=😐 4=🙂 5=😄) |
| `energy` | `"low"` \| `"medium"` \| `"high"` \| null | No | |
| `factors` | array of string | No | Tối đa 20 items, mỗi item max 50 ký tự |
| `note` | string \| null | No | max 500 ký tự |

**Response:** `MoodEntryResponse`
- `201 Created` — tạo mới
- `200 OK` — cập nhật (trong vòng 1 giờ đầu)

```json
{
  "id": 12,
  "date": "2026-06-05",
  "mood": 4,
  "energy": "medium",
  "factors": ["tập thể dục", "gia đình"],
  "note": "Hôm nay khá ổn",
  "created_at": "2026-06-05T08:30:00Z",
  "updated_at": "2026-06-05T08:30:00Z"
}
```

---

### GET /api/v1/mood/entries

**Auth:** JWT Bearer

**Query params:**
| Param | Type | Default | Note |
|-------|------|---------|------|
| `start` | date (ISO) | — | Filter từ ngày này trở đi |
| `end` | date (ISO) | — | Filter đến ngày này |
| `limit` | int | 90 | 1–365 |
| `offset` | int | 0 | Pagination offset |

**Response `200`** — array `MoodEntryResponse`, sắp xếp theo `date` DESC.

---

### GET /api/v1/mood/trend

**Auth:** JWT Bearer

**Query params:**
| Param | Type | Default | Note |
|-------|------|---------|------|
| `period` | `"week"` \| `"month"` | `"week"` | week = 7 ngày gần nhất, month = 30 ngày gần nhất |

**Response `200`:**
```json
{
  "period": "week",
  "start": "2026-05-30",
  "end": "2026-06-05",
  "entries": [
    { "date": "2026-05-30", "mood": null, "energy": null, "factors": [], "note": null },
    { "date": "2026-05-31", "mood": 3, "energy": "medium", "factors": ["work"], "note": null },
    { "date": "2026-06-01", "mood": 4, "energy": "high", "factors": [], "note": "Tốt" }
  ],
  "best_day": "2026-06-01",
  "worst_day": "2026-05-31",
  "average_mood": 3.5
}
```

| Field | Note |
|-------|------|
| `entries` | Luôn đủ 7 (week) hoặc 30 (month) slots — ngày không có check-in có `mood: null` |
| `best_day` / `worst_day` | `null` khi không có entry nào trong range |
| `average_mood` | `null` khi không có entry nào |

---

### GET /api/v1/mood/heatmap

**Auth:** JWT Bearer

**Query params:**
| Param | Type | Required | Note |
|-------|------|----------|------|
| `year` | int | Yes | 2000–2100 |
| `month` | int | Yes | 1–12 |

**Response `200`:**
```json
{
  "year": 2026,
  "month": 6,
  "days": [
    { "date": "2026-06-01", "mood_score": 4 },
    { "date": "2026-06-03", "mood_score": 2 }
  ]
}
```

`days` là **sparse** — chỉ chứa những ngày có check-in. Ngày không có check-in không xuất hiện trong array.

---

### GET /api/v1/assessments/phq9/history

**Auth:** JWT Bearer

**Query params:**
| Param | Type | Default | Note |
|-------|------|---------|------|
| `limit` | int | 50 | 1–200 |
| `offset` | int | 0 | Pagination offset |

**Response `200`** — array `PHQ9Result`, mới nhất trước:
```json
[
  {
    "id": 2,
    "score": 8,
    "severity": "Mild",
    "answers": [0, 1, 2, 1, 0, 1, 1, 1, 1],
    "questions": ["..."],
    "submitted_at": "2026-06-01T10:00:00Z",
    "suggested_goals": [],
    "score_delta": -4
  },
  {
    "id": 1,
    "score": 12,
    "severity": "Moderate",
    "answers": [1, 2, 2, 2, 1, 1, 1, 1, 1],
    "questions": ["..."],
    "submitted_at": "2026-05-18T10:00:00Z",
    "suggested_goals": ["Tập thể dục 3 lần/tuần"],
    "score_delta": null
  }
]
```

| Field | Note |
|-------|------|
| `score_delta` | `current_score - previous_score`; âm = cải thiện; `null` cho lần đầu tiên |

---

### GET /api/v1/assessments/phq9/reminder

**Auth:** JWT Bearer

**Response `200`:**
```json
{
  "due": true,
  "days_since_last": 15,
  "next_due_in_days": 0,
  "last_submitted_at": "2026-05-21T10:00:00Z"
}
```

**Khi chưa có assessment nào:**
```json
{
  "due": true,
  "days_since_last": null,
  "next_due_in_days": 0,
  "last_submitted_at": null
}
```

| Field | Note |
|-------|------|
| `due` | `true` nếu ≥ 14 ngày từ lần cuối, hoặc chưa từng làm |
| `next_due_in_days` | 0 nghĩa là đến hạn ngay bây giờ |

---

## 3) Error codes

| HTTP | Message | Trường hợp |
|------|---------|-----------|
| 401 | — | Thiếu hoặc sai JWT token |
| 409 | `"Bạn chỉ có thể chỉnh sửa check-in trong vòng 1 giờ sau khi tạo."` | `POST /mood/entries` — entry đã tồn tại và quá 1 giờ |
| 422 | — | `mood` ngoài 1–5; `factors` item vượt 50 ký tự; `note` vượt 500 ký tự; `year`/`month` ngoài range |

---

## 4) FE notes

**Check-in (POST /mood/entries):**
- `date` phải là ngày local của user (`YYYY-MM-DD`), không dùng UTC date từ server — nếu user ở múi giờ UTC+7 lúc 23:30, UTC date sẽ là ngày hôm sau.
- Phân biệt 201 vs 200 để hiện toast "Đã lưu" hay "Đã cập nhật".
- Khi nhận 409, block UI edit và hiện message từ `detail` response — không cần hardcode string.

**Trend chart:**
- `entries` luôn đủ slot (7 hoặc 30) — dùng trực tiếp làm X-axis, không cần build date range phía FE.
- Slot có `mood: null` → vẽ gap trên line chart (đừng nối qua điểm null).
- `best_day` / `worst_day` dùng để highlight điểm trên chart.

**Heatmap:**
- Array `days` là sparse — build grid tháng ở FE, map `days` vào đúng ô, ô không có trong array = empty.

**PHQ-9 history — score_delta:**
- `score_delta < 0` = cải thiện (ví dụ -4 → "giảm 4 điểm"); hiện màu xanh.
- `score_delta > 0` = nặng hơn; hiện màu đỏ.
- `score_delta = null` = lần đầu tiên; không hiện so sánh.

**PHQ-9 reminder:**
- Gọi endpoint này khi user mở app hoặc vào tab đánh giá.
- `due: true` + `last_submitted_at: null` = user chưa từng làm — hiện CTA lần đầu.
- `due: true` + `last_submitted_at != null` = đến hạn làm lại — hiện reminder banner.
- `due: false` → `next_due_in_days` cho biết còn bao nhiêu ngày — có thể hiện countdown nhẹ.
