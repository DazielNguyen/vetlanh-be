# BE spec: Unified reflection feed for “Ghi chép”

## Status

- Priority: P1, after the current UI consolidation.
- The current FE is not blocked by this endpoint. It continues using the existing Journal and Thought Record APIs.
- This endpoint is required when the product wants one chronological feed containing both free-form notes and CBT thought records.

## Product context

The service navigation now exposes one user-facing area named **Ghi chép**, with two entry modes:

1. `journal`: quick, free-form writing.
2. `thought_record`: structured five-step CBT reflection.

The underlying resources must remain separate. The unified feed is a read model only; it must not replace the existing CRUD endpoints or merge the two database schemas.

## Required endpoint

### `GET /api/v1/reflections`

Returns journal entries and thought records in one reverse-chronological feed.

### Query parameters

| Name     | Type                               | Required | Description                                       |
| -------- | ---------------------------------- | -------- | ------------------------------------------------- |
| `type`   | `all \| journal \| thought_record` | No       | Defaults to `all`.                                |
| `q`      | string                             | No       | Case-insensitive search across user-visible text. |
| `limit`  | integer                            | No       | Default `20`, maximum `50`.                       |
| `cursor` | string                             | No       | Opaque cursor returned by the previous response.  |

Cursor pagination is preferred over `offset`, because records from two sources can be inserted while the user is paging.

### Response

```json
{
  "items": [
    {
      "id": "journal:184",
      "resource_id": "184",
      "type": "journal",
      "title": "Một buổi chiều nhẹ hơn",
      "preview": "Hôm nay mình đã thử đi bộ một đoạn...",
      "created_at": "2026-07-21T08:40:12Z",
      "updated_at": "2026-07-21T08:43:09Z"
    },
    {
      "id": "thought_record:26a4f55c",
      "resource_id": "26a4f55c",
      "type": "thought_record",
      "title": "Cuộc họp sáng nay",
      "preview": "Mình nghĩ mọi người không hài lòng với mình...",
      "emotion": "Lo lắng, 70%",
      "created_at": "2026-07-20T02:15:00Z",
      "updated_at": "2026-07-20T02:15:00Z"
    }
  ],
  "next_cursor": "opaque-cursor-or-null"
}
```

## Mapping rules

### Journal

- `id`: `journal:{journal.id}`
- `resource_id`: journal ID serialized as a string
- `type`: `journal`
- `title`: journal title; if null, return `Một ghi chép nhỏ`
- `preview`: plain-text content truncated to 160 characters

### Thought record

- `id`: `thought_record:{thought_record.id}`
- `resource_id`: thought record ID
- `type`: `thought_record`
- `title`: `situation`, truncated to 80 characters
- `preview`: `automatic_thought`, truncated to 160 characters
- `emotion`: existing emotion field

All results must belong to the authenticated user. Do not accept a user ID from the client.

## Search behavior

- Journal search fields: `title`, `content`.
- Thought record search fields: `situation`, `automatic_thought`, `emotion`, `evidence_for`, `evidence_against`.
- Trim the query and ignore it when empty.
- Return `200` with an empty `items` array when there are no matches.

## Existing endpoints retained

The FE will continue to use the existing resource endpoints for create, read, update, and delete:

- `/api/v1/journal`
- `/api/v1/thought-records`
- `/api/v1/journal/prompts/*`
- `/api/v1/thought-records/hints`

The unified endpoint must not perform mutations.

## Optional P2: quick draft support

New journal entries currently cannot autosave until the first explicit save creates an ID. If product analytics show meaningful abandonment during first-time writing, add draft support:

### `POST /api/v1/journal/drafts`

Creates an empty private draft and returns a journal-compatible ID.

### `PATCH /api/v1/journal/drafts/{id}`

Accepts partial `title` and `content`; idempotent and safe for debounced autosave.

### `POST /api/v1/journal/drafts/{id}/publish`

Converts the draft into a normal journal entry. Drafts must never appear in the reflection feed until published.

This P2 work is optional and is not required for the current FE release.

## Acceptance criteria

- Items are globally sorted by `created_at DESC`, not sorted separately per resource type.
- No record from another user can appear in the response.
- `type` filtering and text search work together.
- Pagination produces no duplicates within a stable dataset.
- Deleting or updating an underlying resource is reflected in the feed without stale denormalized content.
- Existing Journal and Thought Record APIs remain backward compatible.
