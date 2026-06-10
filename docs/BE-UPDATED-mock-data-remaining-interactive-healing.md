# Mock Data Remaining — Interactive Healing Services

> Tạo: 2026-06-09
> Plan: `plans/260608-interactive-healing-services/`

Những phần dưới đây vẫn đang dùng **dữ liệu cứng hoặc localStorage-only** sau khi hoàn thành 4 phase. Giao diện hiển thị bình thường nhưng chưa kết nối hoàn toàn với BE.

---

## 1. Breathing timing — 4-7-8 hardcoded (Phase 1) — ✅ BE đã có sẵn, chỉ cần FE đổi cách đọc

**File:** `app/services/exercises/[slug]/page.tsx` — constants `BREATH_INHALE`, `BREATH_HOLD`, `BREATH_EXHALE`

**Hiện tại:**
```ts
const BREATH_INHALE = 4;  // giây
const BREATH_HOLD   = 7;
const BREATH_EXHALE = 8;
```

FE dùng 3 giá trị cố định cho tất cả bài tập breathing thay vì đọc từ API.

**Kết luận (2026-06-10):** BE **không cần thêm field mới**. `ExerciseResponse` đã có sẵn `phases: { label: string; seconds: number }[]` (xem `app/schemas/exercise.py` `BreathingPhase`, và dữ liệu trong `app/services/exercise.py`), tổng quát hơn đề xuất 3-field cố định vì hỗ trợ cả số lượng phase khác nhau:

- `box-breathing`: 4 phase (Hít vào 4 / Giữ 4 / Thở ra 4 / Giữ 4)
- `breathing-4-7-8`: 3 phase (Hít vào 4 / Giữ 7 / Thở ra 8)
- `coherent-breathing`: 2 phase (Hít vào 5 / Thở ra 5)

**Việc cần làm (FE only):** thay vì dùng `BREATH_INHALE/HOLD/EXHALE`, loop qua `exercise.phases` — mỗi phase có `label` để hiển thị và `seconds` để chạy timer. Không cần PATCH/migration BE nào.

---

## 2. After-session feeling — chỉ lưu localStorage, chưa sync BE (Phase 3)

**File:** `app/services/exercises/[slug]/page.tsx` — hàm `resolveFeelingAndComplete`

**Hiện tại:**
```ts
localStorage.setItem(`feeling_after_${slug}_last`, feeling);
// feeling ∈ { "much_better" | "better" | "same" | "worse" }
```

Khi người dùng chọn cảm xúc sau buổi tập, giá trị được lưu vào localStorage với key `feeling_after_{slug}_last`. **Không có API call nào được thực hiện.**

**Hệ quả hiện tại:**
- Dữ liệu mất khi user đổi thiết bị hoặc xóa cache trình duyệt
- AI chatbot và dashboard không có thông tin về cảm xúc hậu tập
- Không thể phân tích trend "cảm xúc sau tập theo thời gian"

**Cần từ BE:**

Option 1 — Log cùng exercise completion:
```
PATCH /api/v1/exercises/log/{log_id}
Body: { "post_session_feeling": "much_better" }
```
FE gọi sau khi `logSession` thành công và user đã chọn feeling.

Option 2 — Endpoint riêng:
```
POST /api/v1/exercises/{slug}/feelings
Body: { "feeling": "better", "logged_at": "2026-06-09T..." }
```

Option 3 — **Giữ localStorage-only** (tạm thời) và chấp nhận client-only data. Khi BE sẵn sàng, FE sẽ flush buffer localStorage lên BE.

---

## 3. Feeling options (FEELINGS array) — hardcoded FE (Phase 3) — ✅ BE đã có endpoint

**File:** `app/services/exercises/[slug]/page.tsx`

**Hiện tại:**
```ts
const FEELINGS = [
  { value: "much_better", emoji: "😌", label: "Rất nhẹ" },
  { value: "better",      emoji: "😊", label: "Nhẹ hơn" },
  { value: "same",        emoji: "😐", label: "Bình thường" },
  { value: "worse",       emoji: "😣", label: "Vẫn căng" },
];
```

**Kết luận (2026-06-10):** BE đã thêm endpoint động:

```
GET /api/v1/exercises/feeling-options   (public, no auth)
```

Response:
```json
[
  { "key": "much_better", "label": "Rất nhẹ", "emoji": "😌" },
  { "key": "better",      "label": "Nhẹ hơn", "emoji": "😊" },
  { "key": "same",        "label": "Bình thường", "emoji": "😐" },
  { "key": "worse",       "label": "Vẫn căng", "emoji": "😣" }
]
```

**Việc cần làm (FE):** thay `FEELINGS` hardcode bằng fetch từ endpoint trên (`key` ↔ `value` cũ). Khi gửi feeling lên `PATCH /api/v1/exercises/logs/{log_id}` thì dùng `key`.

---

## 4. Emoji mood map — 5-key hardcoded (Phase 2)

**File:** `app/services/exercises/components/ExerciseList.tsx`

**Hiện tại:**
```ts
const EMOJI_MOOD_MAP: Record<string, string> = {
  anxious:    "😰",
  sad:        "😢",
  cant_sleep: "🌙",
  need_energy: "⚡",
  angry:      "😤",
};
```

FE filter: server moods có key trong map → hiển thị emoji button lớn. Server moods không có key → hiển thị text pill nhỏ ở row dưới.

**Hệ quả:** Nếu BE thêm mood key mới (ví dụ `stressed`, `lonely`), chúng sẽ xuất hiện là text pill — không có emoji button, không nhất quán UX.

**Cần BE xác nhận:**

- **Hướng A — 5 mood key này là cố định:** FE giữ nguyên hardcode. BE không thêm key mới ngoài 5 key hiện tại.

- **Hướng B — BE muốn control emoji:** Thêm field `emoji` vào response của `GET /api/v1/exercises/mood-filters`:
  ```json
  [
    { "key": "anxious", "label": "Lo lắng", "emoji": "😰" },
    ...
  ]
  ```
  FE bỏ `EMOJI_MOOD_MAP`, đọc `emoji` từ API response.

---

## 5. StressChart — level label và trend text hardcoded (DashboardContent)

**File:** `app/services/components/DashboardContent.tsx` — lines 37–38

**Hiện tại:**
```tsx
<span className="text-4xl font-extrabold text-slate-800">Thấp</span>
<span className="text-sm text-emerald-500 font-medium">~15% tuần này</span>
```

`dashboard.sparkline` (mảng số) được truyền đúng vào `StressChart` component và chart render real data. Nhưng **label "Thấp" và text "~15% tuần này" là hardcode** — không đến từ API.

`DashboardData` type hiện tại không có field nào cho stress level label hay trend percent:
```ts
interface DashboardData {
  greeting: string;
  streak_days: number;
  sparkline: number[];
  // ← không có stress_level, stress_trend
  ...
}
```

**Cần từ BE:** Thêm 2 field vào `GET /api/v1/dashboard` response:
```json
{
  "stress_level_label": "Thấp",
  "stress_trend_text": "~15% tuần này"
}
```

Hoặc thêm `stress_level: "low" | "medium" | "high"` để FE tự map sang label tiếng Việt và tính % từ sparkline. Bàn với BE về cách tiếp cận phù hợp hơn.

---

## Tóm tắt

| # | Phần | File | Trạng thái | Việc cần làm |
|---|------|------|-----------|--------------|
| 1 | Breathing timing (4-7-8) | `[slug]/page.tsx` | ✅ BE đã có `phases[]` | FE đổi sang đọc `exercise.phases` thay vì hardcode |
| 2 | After-session feeling | `[slug]/page.tsx` | ✅ BE đã có `post_session_feeling` | FE gửi PATCH log với `post_session_feeling` |
| 3 | Feeling options array | `[slug]/page.tsx` | ✅ BE đã có endpoint | FE đọc `GET /exercises/feeling-options` thay vì hardcode `FEELINGS` |
| 4 | Emoji mood map | `ExerciseList.tsx` | ✅ BE đã có `emoji` trong mood-filters | FE đọc `emoji` từ `GET /exercises/mood-filters` |
| 5 | StressChart label + trend | `DashboardContent.tsx` | ✅ BE đã có `stress_level` + `stress_trend_text` | FE đọc 2 field mới từ `GET /dashboard` |

**Tất cả 5 mục đã có dữ liệu BE — toàn bộ việc còn lại nằm ở phía FE.**

**Đã tích hợp thật (không cần làm thêm):**

| Endpoint | Dùng ở đâu |
|----------|-----------|
| `GET /api/v1/exercises/recommended` | `QuickReliefCard` — 3 tiles dashboard |
| `GET /api/v1/exercises/categories` | `ExerciseList` — category filter pills |
| `GET /api/v1/exercises/mood-filters` | `ExerciseList` — mood filter buttons |
| `GET /api/v1/exercises/feeling-options` | `[slug]/page.tsx` — post-session feeling picker |
| `POST /api/v1/exercises/log` | Tất cả 3 session types sau khi hoàn thành |
| `PATCH /api/v1/exercises/logs/{log_id}` | Cập nhật `post_session_feeling` sau khi chọn cảm xúc |
| `GET /api/v1/dashboard` | Dashboard — `stress_level`, `stress_trend_text`, `mood_sparkline` |
