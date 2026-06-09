# Mock Data Remaining — Interactive Healing Services

> Tạo: 2026-06-09
> Plan: `plans/260608-interactive-healing-services/`

Những phần dưới đây vẫn đang dùng **dữ liệu cứng hoặc localStorage-only** sau khi hoàn thành 4 phase. Giao diện hiển thị bình thường nhưng chưa kết nối hoàn toàn với BE.

---

## 1. Breathing timing — 4-7-8 hardcoded (Phase 1)

**File:** `app/services/exercises/[slug]/page.tsx` — constants `BREATH_INHALE`, `BREATH_HOLD`, `BREATH_EXHALE`

**Hiện tại:**
```ts
const BREATH_INHALE = 4;  // giây
const BREATH_HOLD   = 7;
const BREATH_EXHALE = 8;
```

FE dùng 3 giá trị cố định cho tất cả bài tập breathing. `tense_seconds`/`release_seconds` trong `Exercise` là field của PMR — không dùng cho breathing.

**Vấn đề:** Nếu BE muốn config thời gian thở khác nhau theo từng bài (ví dụ bài cho trẻ em dùng 3-5-6 thay vì 4-7-8), FE không đọc được.

**Cần BE xác nhận một trong hai hướng:**

- **Hướng A — Enum cố định:** 4-7-8 là spec vĩnh viễn, không cần thay đổi per-exercise. FE giữ nguyên constants.

- **Hướng B — Config per-exercise:** Thêm 3 field vào `Exercise` model:
  ```json
  {
    "inhale_seconds": 4,
    "hold_seconds": 7,
    "exhale_seconds": 8
  }
  ```
  FE sẽ đọc từ `exercise.inhale_seconds ?? 4` v.v.

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

## 3. Feeling options (FEELINGS array) — hardcoded FE (Phase 3)

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

4 lựa chọn cố định, không đến từ API. Nếu BE muốn thêm option hoặc thay label thì cần sửa FE code.

**Cần BE xác nhận:** 4-value enum này có phải spec vĩnh viễn không, hay cần API `GET /api/v1/exercises/feeling-options` để FE đọc động?

> **Ghi chú:** Đây là phần có rủi ro thấp nhất — 4 cảm xúc này khá ổn định theo domain. Nếu BE đồng ý enum cố định thì không cần làm thêm.

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
| 1 | Breathing timing (4-7-8) | `[slug]/page.tsx` | Hardcode FE | BE confirm enum cố định hoặc thêm field per-exercise |
| 2 | After-session feeling | `[slug]/page.tsx` | localStorage-only | BE thêm endpoint POST feeling, hoặc confirm client-only |
| 3 | Feeling options array | `[slug]/page.tsx` | Hardcode FE | BE confirm 4-value enum vĩnh viễn |
| 4 | Emoji mood map | `ExerciseList.tsx` | Hardcode FE | BE confirm 5 key cố định hoặc thêm `emoji` field vào mood-filters API |
| 5 | StressChart label + trend | `DashboardContent.tsx` | Hardcode FE | BE thêm `stress_level_label` + `stress_trend_text` vào dashboard response |

**Đã tích hợp thật (không cần làm thêm):**

| Endpoint | Dùng ở đâu |
|----------|-----------|
| `GET /api/v1/exercises/recommended` | `QuickReliefCard` — 3 tiles dashboard |
| `GET /api/v1/exercises/categories` | `ExerciseList` — category filter pills |
| `GET /api/v1/exercises/mood-filters` | `ExerciseList` — mood filter buttons |
| `POST /api/v1/exercises/log` | Tất cả 3 session types sau khi hoàn thành |
