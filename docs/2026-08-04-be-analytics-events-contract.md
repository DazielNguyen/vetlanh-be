# BE Contract — Analytics Events & Admin Reporting

> Date: 2026-08-04
> Author: FE team
> Status: Awaiting BE implementation

Tài liệu này mô tả contract API cần backend triển khai để phục vụ trang **Admin Analytics Dashboard** mới (traffic, tính năng dùng nhiều nhất, tỉ lệ chuyển đổi Free→Pro, MAU theo tháng). Repo FE hiện tại **không có code backend** — tất cả phần dưới đây là spec để backend team tự implement (DB table, endpoint), FE chỉ implement 4 điểm gọi tracking + trang admin đọc dữ liệu tổng hợp.

Phân loại theo mức độ ưu tiên:

- 🔴 **P1 — Core feature** — cần làm trước để FE có dữ liệu thật (feature-usage ranking, MAU)
- 🟡 **P2 — Supporting feature** — traffic/page-view, có thể làm sau P1
- ⚪ **Không phụ thuộc events table** — có thể ship độc lập, sớm hơn (conversion rate)

---

## 1. Bảng `events` (raw log) 🔴

Mỗi dòng là một hành động được track (1 lần chat gửi, 1 lần check-in mood, 1 lần nghe bài tập/âm thanh, 1 lần tương tác cộng đồng, hoặc 1 lần xem trang).

```
events
  id            uuid / bigint, primary key
  user_id       string | null      -- null = khách chưa đăng nhập (xem mục 4, page_view ẩn danh)
  event_name    string             -- validate theo allow-list ở mục 3, reject nếu không khớp
  metadata      json               -- payload nhỏ, xem giới hạn kích thước ở mục 2
  created_at    timestamp (UTC)
```

**Index tối thiểu:** `(event_name, created_at)` — các endpoint tổng hợp ở mục 5 đều query theo event_name + khoảng thời gian.

**Retention:** không giới hạn ở giai đoạn MVP (quy mô user hiện tại còn nhỏ) — sẽ đặt policy archive/xóa sau khi có số liệu thực tế về khối lượng.

---

## 2. Endpoint nhận event (ingestion) 🔴

```
POST /api/v1/telemetry/ping
Content-Type: application/json
(không cần Authorization header)
```

**Request body:**
```json
{
  "event_name": "chat_message_sent",
  "user_id": "string | null",
  "metadata": { "...": "tuỳ event, xem mục 3" }
}
```

**Ghi chú quan trọng:**

- **Không yêu cầu bearer token.** FE cố tình gọi endpoint này không qua flow auth chuẩn — vì các lần gửi lúc người dùng đóng tab (`sendBeacon`) không thể đính kèm Authorization header, nên để nhất quán, `user_id` luôn được gửi trực tiếp trong body.
- **`user_id` là optional/nullable** — khách chưa đăng nhập (vào trang landing, login...) vẫn phải được ghi nhận `page_view` với `user_id: null`. Đừng reject request chỉ vì thiếu user_id.
- **Validate `event_name` theo allow-list** (mục 3) — reject (4xx, không lưu) nếu không khớp, để tránh bị nhồi rác vào bảng `events`.
- **Vì endpoint không xác thực, cần chặn lạm dụng ở phía BE:**
  - Giới hạn kích thước `metadata` (đề xuất: vài KB, không cho gửi blob lớn).
  - Áp rate-limit cơ bản theo IP hoặc theo `user_id` (đề xuất: BE tự chọn ngưỡng phù hợp infra hiện có).
  - `user_id` gửi từ client là **có thể giả mạo** (client tự khai, không qua token) — vì vậy các số liệu tổng hợp ở mục 5 chỉ dùng cho báo cáo tổng quan (admin dashboard), **không** dùng làm nguồn dữ liệu đáng tin cậy cho tính năng nào khác liên quan trực tiếp đến quyền lợi của user đó.
- **Response:** nên trả nhanh (`202 Accepted` hoặc `204 No Content`), không cần trả lại dữ liệu.
- **Đặt tên đường dẫn "trung tính"** (không dùng `/events`, `/track`, `/analytics`) — các tên này dễ bị ad-blocker (uBlock, Privacy Badger) chặn theo blocklist mặc định, khiến mất dữ liệu âm thầm. Path gợi ý ở trên (`/telemetry/ping`) chỉ là ví dụ, BE có thể đổi tên miễn giữ tinh thần "không giống pattern analytics phổ biến".

---

## 3. Danh sách event_name hợp lệ (allow-list) 🔴

| event_name | Khi nào FE gửi | metadata gợi ý |
|---|---|---|
| `chat_message_sent` | Người dùng gửi tin nhắn cho AI thành công | `{}` (không cần chi tiết) |
| `mood_checkin_logged` | Check-in mood lưu thành công | `{ "mood": number }` |
| `exercise_played` | Bài tập được **hoàn thành** (không phải lúc bắt đầu) | `{ "exercise_id": "string" }` |
| `sound_played` | Người dùng **chủ động bấm phát** 1 âm thanh thư giãn (không tính nhạc nền tự động) | `{ "sound_id": "string" }` |
| `community_action` | Gửi tin nhắn match trong community (MVP chỉ tính gửi tin, chưa tính report/exit/block) | `{}` |
| `page_view` | Mỗi lần load trang mới HOẶC chuyển route trong app (kể cả khách chưa đăng nhập) | `{ "path": "string" }` |

> **Lưu ý về ngữ nghĩa không đồng nhất:** `exercise_played` tính lúc hoàn thành bài tập, còn `sound_played` tính lúc bắt đầu phát — hai mốc khác nhau, xác nhận có chủ đích (FE quyết định giữ nguyên vì dùng đúng signal thành công đã có sẵn). Khi đọc chart "tính năng dùng nhiều nhất", admin cần hiểu: số liệu bài tập = số lần hoàn thành, số liệu âm thanh = số lần bắt đầu nghe.

---

## 4. Endpoint tổng hợp cho Admin Dashboard 🔴🟡⚪

Tất cả 4 endpoint dưới đây **yêu cầu admin auth** giống mọi endpoint `/admin/*` hiện có (`Authorization: Bearer <admin token>`).

### 4.1 Feature usage ranking 🔴
```
GET /api/v1/admin/analytics/feature-usage?from=YYYY-MM-DD&to=YYYY-MM-DD
```
Response:
```json
[
  { "event_name": "chat_message_sent", "count": 1234 },
  { "event_name": "mood_checkin_logged", "count": 890 }
]
```

### 4.2 Monthly Active Users (MAU) 🔴
```
GET /api/v1/admin/analytics/mau?months=6
```
"Active" = user có ≥1 event thuộc {`chat_message_sent`, `mood_checkin_logged`, `exercise_played`, `sound_played`, `community_action`} trong tháng đó (không tính `page_view` — chỉ đăng nhập/xem trang không tính là "hoạt động").

Response:
```json
[
  { "month": "2026-07", "active_users": 342 },
  { "month": "2026-08", "active_users": 401 }
]
```

### 4.3 Page views / traffic 🟡
```
GET /api/v1/admin/analytics/page-views?from=YYYY-MM-DD&to=YYYY-MM-DD
```
Response:
```json
[
  { "date": "2026-08-01", "count": 512 },
  { "date": "2026-08-02", "count": 488 }
]
```

### 4.4 Free → Pro conversion rate ⚪ (không phụ thuộc bảng events — có thể làm trước)
```
GET /api/v1/admin/analytics/conversion-rate?joined_from=YYYY-MM-DD&joined_to=YYYY-MM-DD
```
Định nghĩa: trong số user có `joinDate` nằm trong khoảng [joined_from, joined_to], bao nhiêu % **đã từng** nâng cấp Pro (không giới hạn nâng cấp trong bao lâu sau khi đăng ký — chỉ cần đã từng lên Pro).

Response:
```json
{
  "joined_count": 500,
  "converted_count": 45,
  "conversion_rate": 0.09
}
```

> Nếu hệ thống hiện tại chưa lưu chính xác thời điểm user chuyển sang Pro (chỉ có `subscription_status` hiện tại + `joinDate`), cần kiểm tra lại xem `grantSubscription` có ghi timestamp đáng tin cậy hay không trước khi implement endpoint này.

---

## Câu hỏi cần BE xác nhận trước khi FE tích hợp Phase 5

- [ ] Path cuối cùng của ingestion endpoint và 4 endpoint tổng hợp (tên gợi ý trong doc này có thể đổi, FE sẽ cập nhật theo).
- [ ] `grantSubscription` hiện có ghi timestamp đủ để tính mục 4.4 không, hay cần thêm field mới?
- [ ] Ngưỡng rate-limit/kích thước metadata cụ thể BE sẽ áp dụng cho endpoint không xác thực ở mục 2.
