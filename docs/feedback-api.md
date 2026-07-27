# Feedback API contract

Tài liệu này mô tả API cần thiết để thay thế mock adapter hiện tại của giao diện Feedback.

## Nguyên tắc

- Người dùng phải đăng nhập khi gửi feedback.
- Backend lấy `user_id`, tên, email và gói tài khoản từ access token/database; không tin các trường định danh do frontend gửi.
- Chỉ admin được đọc danh sách, xem thông tin người dùng, cập nhật trạng thái và ghi chú nội bộ.
- Không tự động thu thập Nhật ký, Tâm trạng, PHQ-9 hoặc Kế hoạch an toàn.
- Không dùng feedback làm nội dung công khai/testimonial nếu chưa có đồng thuận riêng.

## Enums

### Category

```text
interface | performance | journal | assessment | exercises | library |
audio | assistant | settings | safety | other
```

### Status

```text
new | reviewing | planned | resolved | dismissed
```

Luồng thông thường:

```text
new → reviewing → planned → resolved
                  └────────→ dismissed
```

Khi chuyển sang `dismissed`, khuyến nghị bắt buộc có `internal_note`.

## 1. Tạo feedback

```http
POST /api/v1/feedback
Authorization: Bearer <token>
Content-Type: application/json
```

Request:

```json
{
  "rating": 4,
  "categories": ["interface", "audio"],
  "positive_comment": "Giao diện dễ chịu và dễ sử dụng.",
  "improvement_comment": "Player che nội dung trên màn hình nhỏ.",
  "allow_contact": true,
  "source_page": "/services/settings",
  "app_version": "1.0.0"
}
```

Validation:

- `rating`: integer, 1–5, bắt buộc.
- `categories`: 1–5 giá trị hợp lệ, không trùng.
- `positive_comment`: tùy chọn, tối đa 1.500 ký tự.
- `improvement_comment`: bắt buộc, 5–2.000 ký tự.
- `allow_contact`: boolean, mặc định `false`.
- `source_page`: tối đa 500 ký tự; chỉ lưu path/query, không nhận URL chứa token.
- `app_version`: tối đa 50 ký tự.
- Rate limit đề xuất: 5 feedback/người dùng/giờ.

Response `201`:

```json
{
  "id": "fdb_01K2ABC",
  "rating": 4,
  "categories": ["interface", "audio"],
  "positive_comment": "Giao diện dễ chịu và dễ sử dụng.",
  "improvement_comment": "Player che nội dung trên màn hình nhỏ.",
  "allow_contact": true,
  "source_page": "/services/settings",
  "app_version": "1.0.0",
  "status": "new",
  "created_at": "2026-07-27T09:30:00Z"
}
```

## 2. Danh sách feedback cho admin

```http
GET /api/v1/admin/feedback?page=1&page_size=20&rating=1&category=audio&status=new&search=player&sort=-created_at
Authorization: Bearer <admin-token>
```

Query:

- `page`: mặc định 1.
- `page_size`: mặc định 20, tối đa 100.
- `rating`: 1–5.
- `category`: category enum.
- `status`: status enum.
- `search`: tìm trong tên, email, positive/improvement comment.
- `allow_contact`: boolean.
- `subscription_status`: `none | pro | expired`.
- `created_from`, `created_to`: ISO-8601.
- `sort`: `created_at`, `-created_at`, `rating`, `-rating`.

Response:

```json
{
  "items": [
    {
      "id": "fdb_01K2ABC",
      "rating": 4,
      "categories": ["interface", "audio"],
      "positive_comment": "Giao diện dễ chịu.",
      "improvement_comment": "Player che nội dung.",
      "allow_contact": true,
      "source_page": "/services/settings",
      "app_version": "1.0.0",
      "status": "new",
      "internal_note": null,
      "created_at": "2026-07-27T09:30:00Z",
      "user": {
        "id": "usr_01K1",
        "display_name": "Minh Anh",
        "email": "minhanh@example.com",
        "subscription_status": "pro"
      }
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 127
}
```

## 3. Thống kê feedback

```http
GET /api/v1/admin/feedback/stats?created_from=2026-07-01&created_to=2026-07-31
Authorization: Bearer <admin-token>
```

Response:

```json
{
  "total": 127,
  "average_rating": 4.2,
  "unresolved": 18,
  "last_30_days": 23,
  "rating_distribution": {
    "1": 3,
    "2": 7,
    "3": 17,
    "4": 38,
    "5": 62
  },
  "top_categories": [
    { "category": "interface", "count": 31 },
    { "category": "audio", "count": 24 }
  ]
}
```

## 4. Chi tiết feedback

```http
GET /api/v1/admin/feedback/{feedback_id}
Authorization: Bearer <admin-token>
```

Trả về cùng schema item trong API danh sách.

## 5. Cập nhật trạng thái và ghi chú

```http
PATCH /api/v1/admin/feedback/{feedback_id}
Authorization: Bearer <admin-token>
Content-Type: application/json
```

Request:

```json
{
  "status": "planned",
  "internal_note": "Đưa vào sprint cải thiện mobile player."
}
```

Validation:

- `status`: status enum.
- `internal_note`: chỉ admin nhìn thấy, tối đa 4.000 ký tự.
- Ghi audit log gồm admin, trạng thái cũ/mới và thời gian.

Response `200`: feedback record đã cập nhật.

## Mã lỗi

- `400`: payload/query không hợp lệ.
- `401`: chưa đăng nhập.
- `403`: không có quyền admin.
- `404`: feedback không tồn tại.
- `422`: validation error.
- `429`: vượt giới hạn gửi.
- `500`: lỗi máy chủ.

## Thay mock bằng API

Frontend hiện dùng `lib/feedbackMock.ts`. Khi BE hoàn tất:

1. Tạo `lib/api/services/fetchFeedback.ts`.
2. Tạo `hooks/useFeedback.ts` với React Query.
3. Thay `feedbackMock.create/list/update` bằng mutation/query tương ứng.
4. Xóa nhãn “Dữ liệu minh họa” và cảnh báo lưu trong trình duyệt.
5. Giữ nguyên types tại `types/feedback.ts`, hoặc sinh types từ OpenAPI nếu schema BE tương thích.
