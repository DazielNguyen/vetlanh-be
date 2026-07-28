# BE Requirements — Đăng ký email không cần xác minh

**Ngày:** 2026-07-28  
**Trạng thái:** Chờ BE triển khai  
**Phạm vi:** Luồng đăng ký mới bằng email và mật khẩu  
**Không thuộc phạm vi:** Đổi email, quên mật khẩu và xác minh các thao tác nhạy cảm

## 1. Mục tiêu

Vết Lành đã ngừng sử dụng đăng nhập Google. Người dùng đăng ký bằng email/password cần được sử dụng tài khoản ngay, không phải mở email và bấm liên kết xác minh.

Tài liệu này thay thế hành vi đăng ký email trong:

- `docs/2026-06-05-feat-authentication.md`
- `docs/2026-06-08-feat-email-verification-flow.md`

Hai tài liệu cũ vẫn có giá trị đối với tài khoản cũ chưa xác minh và luồng đổi email cho đến khi BE hoàn tất migration.

## 2. Hành vi FE hiện tại

Sau khi `POST /api/v1/auth/register` thành công, FE gọi ngay:

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "plain-password-from-current-form"
}
```

- Nếu login thành công, FE lưu access token và chuyển thẳng đến `/services`.
- Nếu BE cũ trả lỗi chưa xác minh, FE chuyển về `/verify-pending` để tương thích ngược.
- FE không lưu mật khẩu ngoài state của form đăng ký.

Vì vậy có thể deploy FE trước BE mà không làm hỏng luồng production.

## 3. Thay đổi bắt buộc ở BE

### 3.1. `POST /api/v1/auth/register`

Khi tạo tài khoản email mới:

1. Chuẩn hóa email như hiện tại.
2. Kiểm tra email trùng như hiện tại.
3. Hash mật khẩu như hiện tại.
4. Tạo user với:

```python
is_active = True
is_verified = True
```

5. Không tạo email-verification token.
6. Không enqueue task gửi email xác minh.
7. Không phân biệt Gmail với các domain email khác.

Không dùng điều kiện như `email.endswith("@gmail.com")`. Sau khi bỏ xác minh, chính sách phải áp dụng nhất quán cho toàn bộ đăng ký email/password.

### Response tối thiểu

Có thể giữ response hiện tại để không làm vỡ FE:

```json
{
  "id": "user-id",
  "email": "user@example.com",
  "is_active": true,
  "is_verified": true,
  "display_name": null,
  "avatar_url": null,
  "timezone": null,
  "goals": []
}
```

Status đề xuất:

```http
201 Created
```

FE hiện tự gọi `/auth/login`, vì vậy BE chưa bắt buộc trả access token trong response đăng ký.

### Phương án cải tiến tùy chọn

BE có thể trả token trực tiếp để bỏ một request:

```json
{
  "access_token": "...",
  "token_type": "bearer"
}
```

Nếu chọn phương án này, cần thống nhất contract mới với FE trước khi thay đổi response hiện tại.

### 3.2. `POST /api/v1/auth/login`

Tài khoản email tạo theo luồng mới phải đăng nhập được ngay.

BE vẫn phải kiểm tra:

- Email và mật khẩu hợp lệ.
- `is_active = true`.
- Tài khoản không bị khóa hoặc xóa.

BE không được trả lỗi `403 Please verify your email` cho tài khoản mới đã được tạo với `is_verified = true`.

Không nên xóa ngay toàn bộ logic kiểm tra `is_verified`, vì tài khoản cũ có thể vẫn còn ở trạng thái chưa xác minh trong thời gian migration.

## 4. Dữ liệu cũ và migration

### 4.1. Không chạy migration mù

Không chạy trực tiếp:

```sql
UPDATE users SET is_verified = TRUE;
```

Câu lệnh trên có thể mở cả tài khoản test, tài khoản rác, tài khoản bị khóa hoặc bản ghi chưa hoàn chỉnh.

### 4.2. Audit trước migration

BE cần thống kê:

```sql
SELECT
  is_active,
  is_verified,
  account_type,
  COUNT(*) AS total
FROM users
GROUP BY is_active, is_verified, account_type;
```

Tên bảng/cột phải được điều chỉnh theo schema production thực tế.

### 4.3. Migration đề xuất

Chỉ mở tài khoản email/password đang hoạt động:

```sql
UPDATE users
SET
  is_verified = TRUE,
  updated_at = CURRENT_TIMESTAMP
WHERE is_verified = FALSE
  AND is_active = TRUE
  AND account_type = 'email';
```

Nếu schema không có `account_type`, BE phải xác định tài khoản email/password bằng trường/provider thực tế. Không suy luận chỉ từ domain `@gmail.com`.

Nên chạy theo transaction và ghi lại số bản ghi bị ảnh hưởng:

```sql
BEGIN;

-- Chạy UPDATE có RETURNING id hoặc kiểm tra row count.

COMMIT;
```

Trước khi commit production, cần sao lưu hoặc có migration `down` phù hợp với quy trình của dự án.

## 5. Các endpoint xác minh cũ

Trong giai đoạn chuyển tiếp, giữ nguyên:

```http
GET  /api/v1/auth/verify
POST /api/v1/auth/resend-verification
```

Lý do:

- FE hiện vẫn có fallback cho tài khoản cũ.
- Link xác minh đã gửi trước đây có thể vẫn được người dùng mở.
- Cần tránh làm hỏng bookmark hoặc email cũ ngay sau deploy.

Sau khi migration hoàn tất và hết thời gian sống tối đa của verification token:

- Có thể cho các endpoint trả `410 Gone`, hoặc
- Giữ idempotent và trả thông báo tài khoản đã sử dụng được.

Không trả thông tin cho biết một email có tồn tại hay không.

## 6. Luồng đổi email vẫn phải xác minh

Không thay đổi bảo mật của:

```http
PATCH /api/v1/users/me/email
GET   /api/v1/auth/verify-email-change
```

Đổi email là thao tác nhạy cảm. Email mới vẫn nên được xác minh trước khi thay thế email đang dùng.

Việc bỏ xác minh khi đăng ký không đồng nghĩa bỏ xác minh đổi email hoặc quên mật khẩu.

## 7. Xử lý lỗi

### Email đã tồn tại

```http
409 Conflict
```

```json
{
  "detail": "Email already registered"
}
```

Không tạo thêm user và không gửi email xác minh.

### Mật khẩu không hợp lệ

```http
422 Unprocessable Entity
```

Giữ chính sách mật khẩu hiện tại.

### Tài khoản bị khóa

```http
403 Forbidden
```

Không được tự kích hoạt lại chỉ vì migration xác minh email.

### Lỗi gửi email

Luồng đăng ký mới không phụ thuộc dịch vụ gửi email, nên lỗi SMTP không được làm đăng ký thất bại.

## 8. Idempotency và race condition

Hai request đăng ký đồng thời với cùng email chỉ được tạo một user.

Yêu cầu:

- Database có unique constraint trên email đã chuẩn hóa.
- BE bắt lỗi unique constraint và trả `409`.
- Không dựa duy nhất vào bước `SELECT` trước `INSERT`.

## 9. Test cases bắt buộc

### Unit/integration

1. Đăng ký email mới trả `201`.
2. User mới có `is_active = true`.
3. User mới có `is_verified = true`.
4. Không tạo verification token.
5. Không gọi email sender.
6. Login ngay sau register trả access token.
7. Email trùng trả `409`.
8. Hai register đồng thời chỉ tạo một user.
9. User bị khóa vẫn không login được.
10. Đổi email vẫn yêu cầu xác minh email mới.

### End-to-end

```text
Mở /register
→ chọn Email
→ nhập email/password
→ POST /auth/register = 201
→ POST /auth/login = 200
→ FE chuyển /services
→ refresh trang vẫn đăng nhập
→ GET /users/me trả is_verified = true
```

### Regression

- Đăng ký bằng username vẫn hoạt động.
- Đăng nhập email cũ vẫn hoạt động.
- Quên mật khẩu vẫn hoạt động.
- Đổi email và verify email mới vẫn hoạt động.
- Admin vẫn xem và quản lý được user.

## 10. Thứ tự deploy production

1. Deploy FE tương thích ngược hiện tại.
2. Kiểm tra đăng ký với BE cũ vẫn chuyển đến `/verify-pending`.
3. Deploy BE thay đổi user mới thành `is_verified = true`.
4. Smoke test register → login → `/services`.
5. Theo dõi lỗi `403 unverified` và tỷ lệ register/login.
6. Audit tài khoản cũ.
7. Chạy migration có kiểm soát nếu sản phẩm quyết định mở tài khoản cũ.
8. Sau thời gian chuyển tiếp mới loại bỏ endpoint verify cũ.

Không cần thêm hoặc thay đổi biến môi trường cho luồng đăng ký mới.

## 11. Rollback

Nếu cần rollback BE:

1. Khôi phục hành vi tạo user mới với `is_verified = false`.
2. Bật lại task gửi email xác minh.
3. Giữ endpoint verify/resend hoạt động.
4. Không tự động đổi các user đã được xác minh về `false`.

FE hiện có fallback `unverified → /verify-pending`, nên rollback BE không yêu cầu rollback FE ngay lập tức.

## 12. Tiêu chí hoàn thành

- [ ] User email mới được tạo với `is_verified = true`.
- [ ] Đăng ký không gửi verification email.
- [ ] Đăng ký xong đăng nhập được ngay.
- [ ] User bị khóa vẫn bị chặn.
- [ ] Đổi email vẫn xác minh.
- [ ] Có unique constraint chống đăng ký trùng.
- [ ] Test unit/integration/E2E đạt.
- [ ] Đã audit tài khoản `unverified` cũ.
- [ ] Đã có kế hoạch migration hoặc quyết định giữ nguyên dữ liệu cũ.
- [ ] Đã kiểm tra rollback.
