# Unified Reflection Feed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add authenticated `GET /api/v1/reflections` with searchable, globally sorted, cursor-paginated Journal and Thought Record items.

**Architecture:** A reflection schema defines the public contract, while a read-only service queries both tenant-scoped source tables and maps them in memory so encrypted journal content remains searchable. A thin FastAPI router validates parameters and delegates to the service; existing CRUD and schemas remain untouched.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2 async, pytest, httpx.

## Global Constraints

- Implement P1 only; journal drafts are excluded.
- Do not add migrations or split the existing Thought Record `evidence` field.
- Never accept a user ID from the client.
- `type` defaults to `all`; `limit` defaults to 20 and is restricted to 1–50.
- Results sort globally by `created_at DESC` with stable type and numeric-ID tie breakers.
- Existing Journal and Thought Record endpoints remain backward compatible.

---

### Task 1: Response contract and pure feed behavior

**Files:**
- Create: `app/schemas/reflection.py`
- Create: `app/services/reflection.py`
- Create: `tests/test_reflections.py`

**Interfaces:**
- Produces: `ReflectionType`, `ReflectionItem`, `ReflectionFeedResponse`.
- Produces: `_plain_text(value: str) -> str`, `_encode_cursor(item: ReflectionItem) -> str`, `_decode_cursor(value: str) -> tuple[datetime, int, int]`, `_map_journal(entry) -> ReflectionItem`, `_map_thought_record(record) -> ReflectionItem`.

- [ ] **Step 1: Write failing pure unit tests**

Add tests that import the interfaces above and assert journal fallback title, HTML/entity cleanup, whitespace normalization, 160/80-character truncation, thought-record emotion, cursor round trip, and malformed cursor rejection.

```python
def test_journal_mapping_uses_fallback_and_plain_preview():
    item = _map_journal(_journal(title=None, content="<p>Hello &amp;  world</p>"))
    assert item.title == "Một ghi chép nhỏ"
    assert item.preview == "Hello & world"

def test_cursor_round_trip():
    item = _map_journal(_journal(id=7))
    assert _decode_cursor(_encode_cursor(item)) == (
        item.created_at, TYPE_RANK[item.type], 7
    )
```

- [ ] **Step 2: Verify RED**

Run: `pytest tests/test_reflections.py -q`

Expected: collection fails because `app.schemas.reflection` and `app.services.reflection` do not exist.

- [ ] **Step 3: Implement schemas and pure helpers**

Define `ReflectionType(str, Enum)` values `all`, `journal`, and `thought_record`. Define response models with timestamps and optional `emotion` excluded when null. Implement plain-text conversion with an `HTMLParser`, `html.unescape`, and whitespace collapsing. Implement deterministic type ranks, mapping, and URL-safe base64 JSON cursors containing version, UTC timestamp, rank, and positive numeric resource ID. Cursor parsing raises `ValueError` on every invalid shape.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/test_reflections.py -q`

Expected: all pure behavior tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/schemas/reflection.py app/services/reflection.py tests/test_reflections.py
git commit -m "feat: add reflection feed read model"
```

### Task 2: Tenant-scoped querying, search, ordering, and pagination

**Files:**
- Modify: `app/services/reflection.py`
- Modify: `tests/test_reflections.py`

**Interfaces:**
- Consumes: mapping and cursor helpers from Task 1.
- Produces: `async list_reflections(db: AsyncSession, user_id: int, reflection_type: ReflectionType = ReflectionType.ALL, q: str | None = None, limit: int = 20, cursor: str | None = None) -> ReflectionFeedResponse`.

- [ ] **Step 1: Write failing service tests**

Use an `AsyncMock` session with ordered execute results. Assert source selection by type, both SQL statements contain the authenticated `user_id` predicate, trimmed empty queries are ignored, casefold search covers decrypted journal title/content and thought-record situation/automatic thought/emotion/evidence, global ordering is stable, and two pages contain no duplicate IDs.

```python
result = await list_reflections(db, 42, q="  LO LẮNG  ", limit=2)
assert [item.id for item in result.items] == expected_ids
assert result.next_cursor is not None
page_two = await list_reflections(db, 42, q="LO LẮNG", limit=2,
                                  cursor=result.next_cursor)
assert set(i.id for i in result.items).isdisjoint(i.id for i in page_two.items)
```

- [ ] **Step 2: Verify RED**

Run: `pytest tests/test_reflections.py -q`

Expected: failures show `list_reflections` is absent or does not provide filtering/pagination.

- [ ] **Step 3: Implement the service**

Issue only the required source queries, each with `.where(Model.user_id == user_id)`. Normalize search as `(q or "").strip().casefold()`, filter mapped-source visible fields, sort descending by `(created_at, type rank, numeric resource ID)`, apply a strict cursor boundary, fetch logically as `limit + 1`, and encode the last returned item when more data exists.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/test_reflections.py -q`

Expected: all service tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/reflection.py tests/test_reflections.py
git commit -m "feat: query and paginate unified reflections"
```

### Task 3: Authenticated API integration

**Files:**
- Create: `app/api/v1/endpoints/reflections.py`
- Modify: `app/api/v1/__init__.py`
- Modify: `tests/test_reflections.py`

**Interfaces:**
- Consumes: `list_reflections` from Task 2 and existing `get_current_user`, `get_db` dependencies.
- Produces: `GET /api/v1/reflections`.

- [ ] **Step 1: Write failing integration tests**

Using the existing registration/login helper pattern, create Journal and Thought Record records through their public APIs. Assert unauthenticated access returns 401; empty feed returns 200; mixed records are globally ordered and correctly mapped; `type` and `q` combine; encrypted content and evidence are searchable; cross-user rows never appear; invalid type/limit/cursor return 422; cursor traversal has no duplicates; updates and deletes appear immediately.

```python
response = await client.get("/api/v1/reflections?type=all&limit=1", headers=_auth(token))
assert response.status_code == 200
assert len(response.json()["items"]) == 1
assert response.json()["next_cursor"]
```

- [ ] **Step 2: Verify RED**

Run: `pytest tests/test_reflections.py -q`

Expected: API tests receive 404 because the route is not registered.

- [ ] **Step 3: Implement and register the router**

Create an `APIRouter(prefix="/reflections", tags=["reflections"])`. Validate `q` with maximum 200, `limit` with `ge=1, le=50`, and parse `type` through `ReflectionType`. Decode invalid cursors before querying and raise `HTTPException(422, "Invalid cursor")`. Pass only `current_user.id` to the service and return `ReflectionFeedResponse`. Import and include the router in `app/api/v1/__init__.py`.

- [ ] **Step 4: Verify feature and regressions**

Run: `pytest tests/test_reflections.py tests/test_journal.py tests/test_thought_records.py -q`

Expected: all selected tests pass with zero failures.

- [ ] **Step 5: Run quality checks**

Run: `ruff check app/schemas/reflection.py app/services/reflection.py app/api/v1/endpoints/reflections.py tests/test_reflections.py app/api/v1/__init__.py`

Run: `black --check app/schemas/reflection.py app/services/reflection.py app/api/v1/endpoints/reflections.py tests/test_reflections.py app/api/v1/__init__.py`

Expected: both commands exit 0.

- [ ] **Step 6: Commit**

```bash
git add app/api/v1/endpoints/reflections.py app/api/v1/__init__.py tests/test_reflections.py
git commit -m "feat: expose unified reflection feed API"
```

### Task 4: Final verification

**Files:**
- Review: `docs/Update_21_07_2026/unified-reflection-feed-api-requirements.md`
- Review: `docs/superpowers/specs/2026-07-21-unified-reflection-feed-design.md`
- Review: all files changed by Tasks 1–3.

**Interfaces:**
- Consumes: complete API from Tasks 1–3.
- Produces: evidence that the feature and existing application remain valid.

- [ ] **Step 1: Check requirement coverage and diff hygiene**

Run: `git diff --check`

Run: `git status --short`

Confirm every P1 acceptance criterion has an integration or service assertion and that unrelated existing working-tree changes were not modified.

- [ ] **Step 2: Run the full test suite**

Run: `pytest -q`

Expected: zero failed tests.

- [ ] **Step 3: Report exact verification evidence**

Report the feature files, endpoint behavior, test counts, lint/format results, and any pre-existing unrelated worktree changes. Do not claim completion unless each fresh command exits successfully.
