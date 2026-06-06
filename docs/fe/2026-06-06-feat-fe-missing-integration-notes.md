# FE Handoff: FE-Missing Integration — Implementation Notes

> Branch: `dev`
> Date: 2026-06-06
> Source: `plans/mock-data-remaining-fe-missing.md`

Tất cả 5 items dưới đây là **FE-side only** — BE endpoints đã sẵn sàng. Không cần thay đổi BE.

---

## 1) Endpoint map

Không có endpoint mới. Tất cả đã tồn tại:

- `GET /api/v1/users/me/mood-summary?days=7` — trả `[{ date, sentiment_score }]`
- `GET /api/v1/exercises/recommended?mood={filter}&limit=3` — trả exercises

---

## 2) Implementation notes

### Item 1 — LiveInsights: Mood param từ latest check-in

**File:** `app/services/chat/components/LiveInsights.tsx`

**Vấn đề:** `mood` param đang hardcode `"anxious"`.

**Giải pháp:** Lấy `sentiment_score` từ `GET /users/me/mood-summary?days=1`, map sang `MoodFilter`:

```ts
function scoreToMoodFilter(score: number | undefined): MoodFilter {
  if (score === undefined) return "anxious"; // fallback
  if (score <= 2) return "sad";
  if (score === 3) return "anxious";
  return "need_energy"; // score 4–5
}
```

**Call order:** Fetch mood-summary trước, sau đó truyền kết quả vào `useRecommendedExercises`.

```ts
const { data: moodSummary } = useMoodSummary({ days: 1 });
const latestScore = moodSummary?.[0]?.sentiment_score;
const moodFilter = scoreToMoodFilter(latestScore);

const { data: exercises } = useRecommendedExercises({ mood: moodFilter, limit: 3 });
```

**Pitfall:** `moodSummary` có thể là mảng rỗng (user chưa check-in hôm nay) — dùng `moodSummary?.[0]` và fallback về `"anxious"`.

---

### Item 2 — LiveInsights: Chart 7 slot với visual gap

**File:** `app/services/chat/components/LiveInsights.tsx`

**Vấn đề:** Response từ `GET /users/me/mood-summary?days=7` là sparse — chỉ ngày có check-in được trả về. Nếu render trực tiếp, bars chỉ hiện ngày có data, không có gap cho ngày bỏ lỡ.

**Giải pháp:** Build mảng 7 slot cố định trên FE, merge với data từ BE:

```ts
function buildChartSlots(
  entries: { date: string; sentiment_score: number }[],
  days = 7
): { date: string; score: number | null }[] {
  const byDate = Object.fromEntries(entries.map(e => [e.date, e.sentiment_score]));
  const today = new Date();

  return Array.from({ length: days }, (_, i) => {
    const d = new Date(today);
    d.setDate(today.getDate() - (days - 1 - i));
    const dateStr = d.toISOString().split("T")[0];
    return { date: dateStr, score: byDate[dateStr] ?? null };
  });
}
```

**Render:** Slot có `score === null` → render bar với opacity thấp hoặc placeholder dash.

---

### Item 3 — Crisis button route

**File:** `app/services/chat/components/LiveInsights.tsx`

**Đây là product decision — không phải FE bug.** Hai lựa chọn:

| Option | Code | Khi nào dùng |
|--------|------|--------------|
| Hotline ngoài | `href="tel:18006898"` | Không có trang crisis nội bộ |
| Route nội bộ | `href="/services/crisis"` | Khi trang `/services/crisis` đã được build |

Nếu cả hai chưa quyết định, giữ `tel:18006898` làm default an toàn.

---

### Item 4 — MoodInsights: Delta color âm/dương

**File:** `app/services/mood/components/MoodInsights.tsx` (line 65)

**Vấn đề:** `delta` từ BE là `float | null`. Giá trị dương = cải thiện (xanh), âm = tệ hơn (đỏ).

**Sửa:**

```tsx
// Trước:
<span className="text-emerald-600">+{item.delta}</span>

// Sau:
{item.delta !== null && (
  <span className={item.delta >= 0 ? "text-emerald-600" : "text-red-500"}>
    {item.delta >= 0 ? "+" : ""}{item.delta.toFixed(1)}
  </span>
)}
```

**Note:** `overall_average` type luôn có `delta === null` — guard `item.delta !== null` trước khi render.

---

### Item 5 — Journal prompts: Topic filter UI

**File:** `hooks/useJournalPrompts.ts` đã có `usePromptsByTopic(topic)`.

**Không blocking** — hook sẵn sàng. Khi cần build UI:

- `GET /api/v1/journal/prompts/daily` trả `topics: string[]` — dùng làm options cho filter dropdown
- Pass topic string vào `usePromptsByTopic(topic)` → `GET /api/v1/journal/prompts?topic={topic}`
- Nếu `topic = null/undefined` → trả toàn bộ prompts

---

## 3) Error codes

Không có error code mới từ phía BE. Xem [2026-06-06-feat-fe-missing-integration.md](./2026-06-06-feat-fe-missing-integration.md) cho error codes đầy đủ.

---

## 4) FE notes

- **Thứ tự ưu tiên:** Item 4 (delta color) là bug dễ fix nhất — 3 dòng. Làm trước.
- **Item 1 và 2** liên quan đến cùng component `LiveInsights.tsx` — nên làm cùng lúc.
- **Item 5** không cần làm ngay — hook đã sẵn sàng, chờ product confirm UI.
- **Score → MoodFilter mapping** không cần BE endpoint mới. FE tự xử lý client-side với hàm `scoreToMoodFilter` ở trên.
