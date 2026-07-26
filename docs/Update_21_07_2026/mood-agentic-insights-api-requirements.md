
DONE
# BE requirements: Agentic mood reflection

**Feature:** `/services/mood` — check-in một chạm và phản hồi cá nhân hóa  
**Priority:** P0  
**Frontend status:** Đã chuẩn bị UI và type theo contract này; tương thích ngược với response insight hiện tại.

## 1. Mục tiêu

Sau khi người dùng chọn một mức tâm trạng, frontend lưu check-in ngay bằng endpoint hiện tại. Backend tạo một phản hồi ngắn dựa trên dữ liệu mood của đúng người dùng, chọn tối đa một hành động phù hợp và trả kết quả có cấu trúc cho card “Điều mình nhận thấy”.

Agent không được chẩn đoán, khẳng định quan hệ nhân quả hoặc tự tạo số liệu. Mọi evidence định lượng phải đến từ lớp thống kê deterministic của backend.

## 2. Luồng yêu cầu

```text
POST /api/v1/mood/entries
  -> upsert thành công ngay
  -> enqueue/recompute analysis cho entry version mới
  -> frontend invalidate GET /api/v1/mood/insights

GET /api/v1/mood/insights
  -> status=processing: frontend poll mỗi 1.5 giây
  -> status=ready: frontend dừng poll và render reflection/action
  -> status=unavailable: frontend dùng rules-based insights hoặc empty state
```

Không để việc gọi model làm chậm thao tác lưu mood. Job phải idempotent theo `(user_id, entry_id, updated_at)`.

## 3. Endpoint giữ nguyên

### `POST /api/v1/mood/entries`

Giữ nguyên request/response hiện tại. Sau khi transaction lưu thành công:

1. Đánh dấu analysis mới nhất của user là stale.
2. Enqueue job tạo reflection cho entry vừa upsert.
3. Nếu cùng một entry bị sửa liên tiếp, chỉ kết quả của version `updated_at` mới nhất được publish.

Việc enqueue lỗi không được làm request lưu check-in thất bại.

### `GET /api/v1/mood/insights`

Mở rộng response hiện tại; không xóa `total_entries`, `has_enough_data` hoặc `insights` để giữ tương thích ngược.

**Auth:** JWT Bearer, chỉ đọc dữ liệu của user hiện tại.  
**Query params:** Không có.

#### Response khi agent đang xử lý

```json
{
  "status": "processing",
  "analysis_for_entry_id": "mood-entry-184",
  "total_entries": 4,
  "has_enough_data": false,
  "insights": [],
  "generated_by": "rules",
  "generated_at": null,
  "reflection": null,
  "next_action": null,
  "follow_up_prompt": null
}
```

#### Response hoàn chỉnh

```json
{
  "status": "ready",
  "analysis_for_entry_id": "mood-entry-184",
  "total_entries": 12,
  "has_enough_data": true,
  "generated_by": "agent",
  "generated_at": "2026-07-21T09:42:18Z",
  "reflection": {
    "acknowledgement": "Có vẻ hôm nay bạn đang có ít năng lượng hơn thường lệ.",
    "observation": "Trong những lần bạn ghi nhận thiếu ngủ gần đây, tâm trạng thường thấp hơn mức trung bình của bạn.",
    "evidence": "3 trong 4 lần có yếu tố giấc ngủ",
    "confidence": "medium"
  },
  "next_action": {
    "type": "exercise",
    "title": "Thử thở chậm trong 2 phút",
    "description": "Một bước ngắn để cơ thể dịu lại",
    "url": "/services/exercises/breathing-2-min"
  },
  "follow_up_prompt": "Giúp tôi nhìn kỹ hơn mối liên hệ giữa giấc ngủ và tâm trạng gần đây.",
  "insights": [
    {
      "type": "overall_average",
      "text": "Trong 12 ngày ghi lại, tâm trạng trung bình của bạn là 3.2/5.",
      "delta": null
    },
    {
      "type": "factor_correlation",
      "text": "Những ngày có yếu tố giấc ngủ, tâm trạng thấp hơn trung bình 0.7 điểm.",
      "delta": -0.7
    }
  ]
}
```

#### Response khi model không khả dụng

```json
{
  "status": "unavailable",
  "analysis_for_entry_id": "mood-entry-184",
  "total_entries": 12,
  "has_enough_data": true,
  "generated_by": "rules",
  "generated_at": "2026-07-21T09:42:18Z",
  "reflection": null,
  "next_action": null,
  "follow_up_prompt": null,
  "insights": [
    {
      "type": "overall_average",
      "text": "Trong 12 ngày ghi lại, tâm trạng trung bình của bạn là 3.2/5.",
      "delta": null
    }
  ]
}
```

## 4. Field contract

| Field                   | Type                                 | Bắt buộc | Quy tắc                                                                          |
| ----------------------- | ------------------------------------ | -------: | -------------------------------------------------------------------------------- |
| `status`                | `processing \| ready \| unavailable` |       Có | Trạng thái job agent mới nhất                                                    |
| `analysis_for_entry_id` | `string \| null`                     |       Có | Entry/version mà kết quả đang phản ánh                                           |
| `total_entries`         | integer                              |       Có | Giữ semantics hiện tại                                                           |
| `has_enough_data`       | boolean                              |       Có | Chỉ áp dụng cho insight theo tuần; reflection hôm nay vẫn có thể sinh từ lần đầu |
| `generated_by`          | `rules \| agent`                     |       Có | Không gắn nhãn AI nếu chỉ chạy rules                                             |
| `generated_at`          | ISO-8601 UTC hoặc null               |       Có | Thời điểm publish kết quả                                                        |
| `reflection`            | object hoặc null                     |       Có | Phản hồi chính trên UI                                                           |
| `next_action`           | object hoặc null                     |       Có | Tối đa một hành động                                                             |
| `follow_up_prompt`      | string hoặc null                     |       Có | Prompt dùng để handoff sang chat                                                 |
| `insights`              | array                                |       Có | Giữ schema hiện tại làm evidence/fallback                                        |

### `reflection`

| Field             | Type                    | Giới hạn                                                         |
| ----------------- | ----------------------- | ---------------------------------------------------------------- |
| `acknowledgement` | string                  | 1 câu, tối đa 140 ký tự                                          |
| `observation`     | string                  | 1–2 câu, tối đa 260 ký tự                                        |
| `evidence`        | string hoặc null        | Tối đa 100 ký tự; chỉ dùng số liệu do backend tính               |
| `confidence`      | `low \| medium \| high` | Dựa trên sample size và độ mạnh thống kê, không để model tự chọn |

### `next_action`

| Field         | Type                                  | Quy tắc                                                         |
| ------------- | ------------------------------------- | --------------------------------------------------------------- |
| `type`        | `exercise \| journal \| chat \| rest` | Enum cố định                                                    |
| `title`       | string                                | Tối đa 80 ký tự                                                 |
| `description` | string hoặc null                      | Tối đa 120 ký tự                                                |
| `url`         | string                                | Chỉ relative path bắt đầu bằng `/`, không nhận URL ngoài domain |

## 5. Context và tools cho agent

Agent chạy server-side dưới `user_id` lấy từ JWT. Không nhận raw context do frontend gửi lên.

Phase đầu chỉ cấp các tool sau:

```text
get_latest_mood_entry(user_id)
get_mood_history(user_id, days=14)
get_mood_statistics(user_id, days=30)
find_suitable_exercises(mood, energy, max_minutes=5)
```

`get_mood_statistics` phải trả dữ liệu đã tính sẵn:

- Trung bình và xu hướng 7/14/30 ngày.
- Sample size.
- Factor correlation đủ điều kiện.
- Ngày/khung thời gian nổi bật.
- Missing-data indicator.

Không cho model tự tính trung bình hoặc correlation từ văn bản. Không đọc journal, PHQ-9, safety plan hoặc lịch sử chat trong phase này. Nếu mở rộng về sau phải có consent riêng và audit log.

## 6. Quy tắc tạo nội dung

- Viết tiếng Việt, giọng bình tĩnh, cụ thể và không phán xét.
- Không dùng từ “chắc chắn”, “do”, “gây ra” cho tương quan; dùng “có vẻ”, “thường đi cùng”.
- Không chẩn đoán bệnh hoặc đề nghị thay đổi thuốc/điều trị.
- Không ép người dùng duy trì streak.
- Chỉ nêu một observation chính và tối đa một next action.
- Khi evidence yếu, đặt `confidence=low`, `evidence=null` và chỉ phản hồi check-in hôm nay.
- Không nhắc đến dữ liệu mà user chưa cung cấp.
- Không trả Markdown/HTML trong các field text.

## 7. Safety

Trước khi gọi model, chạy lớp kiểm tra nguy cơ trên `note` mới nhất. Model không phải lớp duy nhất phát hiện khủng hoảng.

- Nếu phát hiện nguy cơ tự hại/khẩn cấp: không trả exercise thông thường.
- `next_action.type` chuyển thành `chat` hoặc route an toàn do sản phẩm quy định.
- Không hiển thị suy luận nhạy cảm như một chẩn đoán.
- Ghi audit event nhưng không log raw note vào application log/prompt observability mặc định.
- Prompt/model output phải qua schema validation và safety post-check trước khi lưu.

## 8. Cache, timeout và retry

- Cache theo `(user_id, entry_id, updated_at, prompt_version)`.
- Mục tiêu hoàn thành job: p95 dưới 5 giây.
- Model timeout: 8 giây; retry tối đa một lần với backoff.
- Sau lỗi cuối, publish `status=unavailable` cùng rules-based `insights`.
- `processing` không được tồn tại quá 15 giây; worker/reaper phải chuyển job treo sang `unavailable`.
- Response không được dùng chung cache giữa các user; thêm `Cache-Control: private, no-store` nếu đi qua shared proxy.

## 9. Error contract

| HTTP | Trường hợp                                                                         |
| ---: | ---------------------------------------------------------------------------------- |
|  200 | Luôn dùng cho `processing`, `ready`, `unavailable`                                 |
|  401 | JWT thiếu hoặc không hợp lệ                                                        |
|  429 | Chỉ khi endpoint bị abuse; polling hợp lệ không được tính như model generation mới |
|  500 | Chỉ khi không thể đọc cả dữ liệu rules-based; không dùng cho lỗi model đơn thuần   |

## 10. Acceptance criteria

- [ ] Chọn mood và lưu entry không phải chờ model.
- [ ] Sau upsert, `GET /mood/insights` phản ánh đúng `analysis_for_entry_id` mới nhất.
- [ ] User mới có thể nhận acknowledgement; không bắt buộc đủ 7 ngày.
- [ ] Insight định lượng chỉ xuất hiện khi đủ sample và khớp kết quả deterministic.
- [ ] Endpoint cũ vẫn trả `insights` để frontend cũ không vỡ.
- [ ] Lỗi/timeout model trả `unavailable`, không làm mất check-in.
- [ ] URL action chỉ là relative path đã allowlist.
- [ ] Không đọc dữ liệu của user khác trong mọi tool call.
- [ ] Output sai schema bị reject và chuyển sang fallback.
- [ ] Có test cho stale job: sửa cùng entry hai lần, kết quả version cũ không được publish.

## 11. Test cases tối thiểu

1. User lần đầu check-in: `has_enough_data=false` nhưng có acknowledgement an toàn.
2. User có 14 ngày dữ liệu và factor đủ mẫu: observation/evidence khớp statistics.
3. Không có factor đủ mẫu: không tạo correlation.
4. Model timeout: `status=unavailable`, rules insight vẫn có.
5. Sửa check-in khi job cũ đang chạy: chỉ job mới nhất được trả về.
6. Exercise đã ẩn/xóa: backend không trả URL đó.
7. Note có tín hiệu khủng hoảng: không trả CTA exercise thông thường.
8. Token của user A không thể lấy analysis của user B.
