# Unified Reflection Feed Design

## Scope

Implement the P1 read-only endpoint `GET /api/v1/reflections`. It combines the authenticated user's journal entries and CBT thought records into one reverse-chronological feed. Existing Journal and Thought Record CRUD APIs and database schemas remain unchanged. Optional journal draft endpoints are out of scope.

The existing Thought Record model has one `evidence` field rather than separate `evidence_for` and `evidence_against` fields. Search therefore uses the existing `evidence` field to preserve API and schema compatibility.

## API contract

The endpoint accepts:

- `type`: `all`, `journal`, or `thought_record`; default `all`.
- `q`: optional string with a maximum length of 200 characters. Leading and trailing whitespace is removed. An empty normalized value disables search.
- `limit`: integer from 1 through 50; default 20.
- `cursor`: optional opaque cursor returned by an earlier response.

The response contains `items` and `next_cursor`. Each item contains `id`, `resource_id`, `type`, `title`, `preview`, `created_at`, and `updated_at`. Thought-record items also contain `emotion`; journal items omit it. Invalid query values or malformed cursors return FastAPI's standard `422` validation response. No matches return `200` with an empty `items` array and a null cursor.

## Components

Add three focused modules and register the router with the API v1 router:

- `app/schemas/reflection.py` defines the filter enum and response models.
- `app/services/reflection.py` owns source loading, search, mapping, stable sorting, cursor encoding/decoding, and page slicing.
- `app/api/v1/endpoints/reflections.py` validates input, obtains `current_user.id`, calls the service, and exposes no mutation operations.

The service queries the existing tables directly rather than calling the existing list services. This avoids their offset pagination and their source-specific search limitations while leaving their public behavior untouched.

## Data flow and authorization

The endpoint takes the user identity only from `get_current_user`. Both source queries include `user_id == current_user.id`; no client-controlled user ID is accepted.

Depending on `type`, the service loads journal entries, thought records, or both. Journal content is transparently decrypted by the existing `EncryptedText` type. The service then applies normalized search, maps records to the response read model, globally sorts the combined list, applies the cursor boundary, takes `limit + 1` items, and returns at most `limit` items plus a cursor when another item exists.

This is deliberately an on-demand read model. Updating or deleting an underlying record is reflected immediately, with no denormalized feed table or cache to invalidate.

## Search

Search is case-insensitive using Python `casefold()` over user-visible text:

- Journal: `title` and decrypted `content`.
- Thought Record: `situation`, `automatic_thought`, `emotion`, and existing `evidence`.

The application performs search after tenant-scoped reads because Journal content uses randomized Fernet encryption and cannot be meaningfully searched with SQL `ILIKE`. This favors correctness and avoids weakening encryption or adding a searchable plaintext index. If per-user data volume later makes this too expensive, searchable encryption or a separately approved secure index should be designed as another feature.

## Mapping and text handling

Journal mapping:

- `id`: `journal:{id}`
- `resource_id`: decimal ID as a string
- `type`: `journal`
- `title`: stored title, or `Một ghi chép nhỏ` when null
- `preview`: plain-text content truncated to 160 Unicode code points

Thought Record mapping:

- `id`: `thought_record:{id}`
- `resource_id`: decimal ID as a string
- `type`: `thought_record`
- `title`: `situation` truncated to 80 Unicode code points
- `preview`: `automatic_thought` truncated to 160 Unicode code points
- `emotion`: existing emotion value

“Plain text” means HTML tags are removed before truncation and HTML entities are unescaped. Whitespace is normalized to single spaces so previews remain suitable for a compact feed. Stored titles are returned as specified except for the thought-record truncation and journal null fallback.

## Ordering and cursor

Items use a deterministic descending sort key:

1. `created_at`
2. resource type rank
3. numeric resource ID

The resource type rank makes ties deterministic across tables; numeric ID makes ties deterministic within a table. The cursor is URL-safe base64-encoded JSON containing a version and the complete sort key of the last returned item. It exposes no user identity and is treated as opaque by clients.

On subsequent requests, only records strictly after that boundary in descending traversal are eligible. This prevents duplicates for a stable dataset. New records inserted above the boundary do not shift later pages. As with ordinary keyset pagination, deleting unseen records can shorten later pages, and changing an existing record's `created_at` would change its position; current update APIs do not change `created_at`.

The cursor does not encode `type`, `q`, or `limit`. Clients are expected to discard a cursor when changing filters, matching common keyset API behavior. A syntactically valid cursor can be used with a changed filter without leaking data; it merely applies its time boundary to the new filtered result.

## Error handling

Schema validation rejects unsupported `type`, out-of-range `limit`, overlong `q`, and malformed cursor values with `422`. Cursor decoding validates the version, timestamp, type rank, and positive numeric resource ID. Authentication failures retain the project's existing `401` behavior. Database and decryption failures use existing application-level error handling and are not silently converted to an empty feed.

## Testing

Development follows red-green-refactor. Service tests cover cursor round trips and rejection, plain-text normalization, field mapping, Unicode truncation, search normalization, evidence search, type filtering, stable global ordering, and page boundaries.

API integration tests cover:

- authentication and cross-user isolation;
- empty results and response shape;
- journal and thought-record mapping;
- global ordering across both tables;
- `type` and `q` together;
- search of encrypted Journal content and Thought Record evidence;
- `limit` validation and multi-page cursor traversal without duplicates;
- malformed cursor handling;
- immediate reflection of updates and deletes;
- unchanged behavior of the existing resource endpoints through the full regression suite.

## Explicit non-goals

- Journal draft creation, autosave, or publication.
- Database migrations or splitting the existing `evidence` field.
- Offset pagination.
- A denormalized feed table, plaintext search column, external search service, or cache.
- Changes to existing Journal or Thought Record CRUD contracts.
