# FE Handoff: Insights Cá Nhân (Epic E3 — US-014)

> Branch: `dev`
> Date: 2026-06-05
> Epic: E3 — US-014: phân tích pattern tâm trạng từ dữ liệu check-in lịch sử

---

## 1) Endpoint map

- `GET /api/v1/mood/insights` — Lấy insights tâm trạng cá nhân được phân tích từ toàn bộ lịch sử check-in

---

## 2) Contracts

### GET /api/v1/mood/insights

`GET /api/v1/mood/insights`

**Auth:** JWT Bearer (any authenticated user)

**Query params:** Không có

**Response `200`:**
```json
{
  "total_entries": 15,
  "has_enough_data": true,
  "insights": [
    {
      "type": "overall_average",
      "text": "Trong 15 ngày ghi lại, tâm trạng trung bình của bạn là 3.4/5.",
      "delta": null
    },
    {
      "type": "day_of_week",
      "text": "Tâm trạng của bạn thường tốt hơn vào thứ Hai (cao hơn trung bình 0.8 điểm).",
      "delta": 0.8
    },
    {
      "type": "factor_correlation",
      "text": "Những ngày có 'tập thể dục', tâm trạng của bạn cao hơn trung bình 1.2 điểm.",
      "delta": 1.2
    }
  ]
}
```

**Response khi chưa đủ dữ liệu (< 7 entries):**
```json
{
  "total_entries": 3,
  "has_enough_data": false,
  "insights": []
}
```

| Field | Type | Note |
|-------|------|------|
| `total_entries` | int | Tổng số ngày đã check-in |
| `has_enough_data` | boolean | `false` khi < 7 entries — hiện empty state thay vì render insights |
| `insights` | array | Luôn rỗng khi `has_enough_data = false` |

**InsightItem fields:**
| Field | Type | Note |
|-------|------|------|
| `type` | `"overall_average"` \| `"day_of_week"` \| `"factor_correlation"` | Dùng để chọn icon/màu sắc phù hợp |
| `text` | string | Câu tiếng Việt render thẳng, đã hoàn chỉnh |
| `delta` | float \| null | `null` cho `overall_average`; số điểm chênh lệch so với trung bình cho 2 type còn lại |

---

## 3) Error codes

| HTTP | Trường hợp |
|------|-----------|
| 401 | Thiếu hoặc sai JWT token |

> Endpoint này không có 404 — user chưa có data sẽ nhận `has_enough_data: false` với `total_entries: 0`.

---

## 4) FE notes

**Empty state:**
- Khi `has_enough_data = false`, hiện message động dựa trên `total_entries`: ví dụ "Bạn cần thêm {7 - total_entries} ngày check-in nữa để xem insights." — số liệu chính xác hơn chuỗi cứng.

**Insight types & hiển thị gợi ý:**
- `overall_average` — luôn xuất hiện đầu tiên nếu có; `delta = null`, không cần hiển thị số delta.
- `day_of_week` — có `delta` dương; phù hợp cho tag/badge "ngày tốt nhất trong tuần".
- `factor_correlation` — text chứa tên factor gốc người dùng nhập (free-form, không chuẩn hoá) — render thẳng, không cần translate.

**Thứ tự insights:** Backend trả cố định `overall_average` → `day_of_week` → `factor_correlation` (nếu có đủ điều kiện). Array có thể có 1–3 phần tử; không phải lúc nào cũng đủ 3.

**Ngưỡng tính toán:** Backend chỉ trả `day_of_week` / `factor_correlation` khi delta ≥ 0.3 điểm VÀ mẫu ≥ 2 lần — FE không cần filter, nhận được là đủ điều kiện hiển thị.

**Call order:** Gọi endpoint này sau khi user vào tab Insights; không cần poll — data chỉ thay đổi khi user tạo check-in mới.
