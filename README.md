# vetlanh-be

Backend API for the Vet Lanh mental wellness platform. Built with FastAPI and async PostgreSQL.

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Local Setup](#local-setup)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
  - [Authentication](#authentication)
  - [Users](#users)
  - [PHQ-9 Assessments](#phq-9-assessments)
  - [Mood Tracking](#mood-tracking)
  - [Journal](#journal)
  - [Journal Prompts](#journal-prompts)
  - [Exercises](#exercises)
  - [Chat (AI Companion)](#chat-ai-companion)
  - [Thought Records (CBT)](#thought-records-cbt)
  - [Safety Plan](#safety-plan)
  - [Crisis Resources](#crisis-resources)
  - [Dashboard](#dashboard)
  - [Resources](#resources)
  - [Community](#community)
  - [Wellness](#wellness)
  - [Badges](#badges)
  - [Notifications](#notifications)
  - [Health Check](#health-check)
- [Authentication Guide](#authentication-guide)
- [Streaming Chat Guide](#streaming-chat-guide)

---

## Tech Stack

| Layer      | Technology                            |
| ---------- | ------------------------------------- |
| Framework  | FastAPI 0.115 (Python 3.11)           |
| Database   | PostgreSQL 16 (async via SQLAlchemy)  |
| Migrations | Alembic                               |
| AI Chat    | Groq API (LLaMA 3)                    |
| Auth       | JWT (HS256) + Google OAuth 2.0        |
| Encryption | Fernet (journal content at rest)      |
| Hosting    | Vercel (serverless)                   |

---

## Local Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd vetlanh-be

# 2. Create and activate virtual environment
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment file
cp .env.example .env
# Fill in the required values (see Environment Variables below)

# 5. Start PostgreSQL with Docker
docker compose up -d --wait

# 6. Run database migrations
alembic upgrade head

# 7. Start the development server
uvicorn app.main:app --reload
```

Interactive API docs are available at `http://localhost:8000/docs`.

---

## Environment Variables

| Variable                    | Required | Description                                           |
| --------------------------- | -------- | ----------------------------------------------------- |
| `DATABASE_URL`              | Yes      | PostgreSQL async URL (`postgresql+asyncpg://...`)     |
| `SECRET_KEY`                | Yes      | Random secret for JWT signing (min 32 chars)          |
| `JOURNAL_ENCRYPTION_KEY`    | Yes      | Fernet key for encrypting journal content at rest     |
| `GROQ_API_KEY`              | Yes      | Groq API key for AI chat (LLaMA 3)                   |
| `GOOGLE_CLIENT_ID`          | Yes      | Google OAuth 2.0 client ID                            |
| `GOOGLE_CLIENT_SECRET`      | Yes      | Google OAuth 2.0 client secret                        |
| `GOOGLE_REDIRECT_URI`       | Yes      | OAuth callback URL registered in Google Cloud Console |
| `SMTP_HOST`                 | No       | SMTP host for verification emails                     |
| `SMTP_PORT`                 | No       | SMTP port (default: 587)                              |
| `SMTP_USER`                 | No       | SMTP username                                         |
| `SMTP_PASSWORD`             | No       | SMTP password                                         |
| `FRONTEND_BASE_URL`         | No       | Frontend URL used in verification email links         |

---

## Project Structure

```
app/
  api/v1/endpoints/   — Route handlers (one file per domain)
  services/           — Business logic
  models/             — SQLAlchemy ORM models
  schemas/            — Pydantic request/response schemas
  core/               — Config, security, dependencies
alembic/              — Database migrations
tests/                — Pytest test suite
```

---

## API Reference

**Base URL:** `/api/v1`

All authenticated endpoints require the header:
```
Authorization: Bearer <access_token>
```

---

### Authentication

No authentication required for these endpoints.

| Method | Path                          | Description                                                    |
| ------ | ----------------------------- | -------------------------------------------------------------- |
| POST   | `/auth/register`              | Register a new account. Sends a verification email.            |
| POST   | `/auth/login`                 | Login with email and password. Returns a JWT access token.     |
| GET    | `/auth/verify`                | Verify email from the link sent after registration.            |
| POST   | `/auth/resend-verification`   | Resend the email verification link.                            |
| GET    | `/auth/google`                | Get the Google OAuth authorization URL.                        |
| GET    | `/auth/google/callback`       | Exchange Google authorization code for a JWT access token.     |

**POST /auth/register**
```json
// Request
{ "email": "user@example.com", "password": "password123" }

// Response 201
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true,
  "is_verified": false,
  "goals": [],
  "display_name": null,
  "avatar_url": null,
  "timezone": null
}
```

**POST /auth/login**
```json
// Request
{ "email": "user@example.com", "password": "password123" }

// Response 200
{ "access_token": "<jwt>", "token_type": "bearer" }
```

**GET /auth/verify**
```
Query params: token=<token_from_email>
Response 200: { "message": "Email verified successfully. You can now log in." }
```

**GET /auth/google**
```json
// Response 200
{ "authorization_url": "https://accounts.google.com/o/oauth2/..." }
```

**GET /auth/google/callback**
```
Query params: code=<authorization_code>
Response 200: { "access_token": "<jwt>", "token_type": "bearer" }
```

---

### Users

Authentication required.

| Method | Path                         | Description                                         |
| ------ | ---------------------------- | --------------------------------------------------- |
| GET    | `/users/me`                  | Get the current authenticated user's profile.       |
| PATCH  | `/users/me`                  | Update display name, avatar URL, or timezone.       |
| PUT    | `/users/me/goals`            | Replace the user's selected wellness goals.         |
| GET    | `/users/me/goals/available`  | List all selectable goal options with labels.       |
| GET    | `/users/me/stats`            | Get user activity stats: exercises completed, mood streak. |
| GET    | `/users/me/healing-path`     | Get healing path progress across core self-care tasks. |

**User object:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true,
  "is_verified": true,
  "goals": ["reduce_anxiety", "better_sleep"],
  "display_name": "Nguyen Van A",
  "avatar_url": "https://...",
  "timezone": "Asia/Ho_Chi_Minh"
}
```

**PATCH /users/me — Request body (all fields optional):**
```json
{ "display_name": "New Name", "avatar_url": "https://...", "timezone": "Asia/Ho_Chi_Minh" }
```

**PUT /users/me/goals — Request body:**
```json
{ "goals": ["reduce_anxiety", "better_sleep"] }
```

**GET /users/me/goals/available — Response:**
```json
{
  "goals": [
    { "value": "reduce_anxiety", "label": "Giảm lo âu" },
    { "value": "better_sleep", "label": "Ngủ ngon hơn" }
  ]
}
```

---

### PHQ-9 Assessments

Authentication required (except `/assessments/phq9/questions`).

| Method | Path                           | Description                                                   |
| ------ | ------------------------------ | ------------------------------------------------------------- |
| GET    | `/assessments/phq9/questions`  | Get the 9 PHQ-9 question texts (no auth required).            |
| POST   | `/assessments/phq9`            | Submit a PHQ-9 assessment (9 answers, each 0-3).              |
| GET    | `/assessments/phq9/latest`     | Get the most recent PHQ-9 result.                             |
| GET    | `/assessments/phq9/history`    | Get paginated PHQ-9 history, newest first.                    |
| GET    | `/assessments/phq9/reminder`   | Check if the user is due for reassessment (14-day cycle).     |

**POST /assessments/phq9 — Request body:**
```json
{ "answers": [0, 1, 2, 0, 1, 3, 0, 1, 2] }
```

**PHQ-9 result object:**
```json
{
  "id": 1,
  "score": 8,
  "severity": "mild",
  "answers": [0, 1, 2, 0, 1, 3, 0, 1, 2],
  "questions": ["..."],
  "submitted_at": "2026-06-03T10:00:00Z",
  "suggested_goals": ["reduce_anxiety"],
  "score_delta": -3
}
```

**Severity levels:** `minimal` | `mild` | `moderate` | `moderately_severe` | `severe`

**GET /assessments/phq9/reminder — Response:**
```json
{ "due": true, "days_since_last": 15, "next_due_at": "2026-06-17T00:00:00Z" }
```

**GET /assessments/phq9/history**
```
Query params: limit (default 50, max 200), offset (default 0)
```

---

### Mood Tracking

| Method | Path               | Description                                                        |
| ------ | ------------------ | ------------------------------------------------------------------ |
| POST   | `/mood/entries`    | Create or update a mood check-in for a given date. (auth required) |
| GET    | `/mood/entries`    | List mood entries with optional date range filter. (auth required) |
| GET    | `/mood/insights`   | Get AI-generated insights (requires at least 7 check-ins). (auth)  |
| GET    | `/mood/heatmap`    | Get sparse mood heatmap for a given year and month. (auth)         |
| GET    | `/mood/trend`      | Get mood trend data for the last 7 days or 30 days. (auth)         |
| GET    | `/mood/factors`    | Get the list of mood check-in factors (public).                    |

**POST /mood/entries — Request body:**
```json
{
  "date": "2026-06-03",
  "mood": 4,
  "energy": "medium",
  "factors": ["work", "sleep"],
  "note": "Had a good day overall"
}
```

- `mood`: integer 1-5 (1=very bad, 5=very good)
- `energy`: `"low"` | `"medium"` | `"high"` | null
- First entry for a date → 201 Created. Within 1 hour of creation → 200 OK (update). After 1 hour → 409 Conflict.

**GET /mood/entries**
```
Query params: start (date), end (date), limit (default 90, max 365), offset
```

**GET /mood/heatmap**
```
Query params: year (required), month (required, 1-12)
Response: { "year": 2026, "month": 6, "days": [{ "date": "2026-06-03", "mood_score": 4 }] }
```

**GET /mood/trend**
```
Query params: period ("week" | "month", default "week")
```
```json
{
  "period": "week",
  "start": "2026-05-27",
  "end": "2026-06-03",
  "entries": [{ "date": "2026-05-27", "mood": 3, "energy": "medium", "factors": [], "note": null }],
  "best_day": "2026-06-01",
  "worst_day": "2026-05-28",
  "average_mood": 3.4
}
```

---

### Journal

Authentication required. Journal content is encrypted at rest using Fernet. Search operates on titles only.

| Method | Path                | Description                                          |
| ------ | ------------------- | ---------------------------------------------------- |
| POST   | `/journal`          | Create a new journal entry.                          |
| GET    | `/journal`          | List journal entries with optional title search.     |
| GET    | `/journal/{id}`     | Get a single journal entry by ID.                    |
| PATCH  | `/journal/{id}`     | Update title or content of a journal entry.          |
| DELETE | `/journal/{id}`     | Delete a journal entry.                              |

**POST /journal — Request body:**
```json
{ "title": "My day", "content": "Today I felt calm..." }
```

**Journal entry object:**
```json
{
  "id": 1,
  "title": "My day",
  "content": "Today I felt calm...",
  "created_at": "2026-06-03T10:00:00Z",
  "updated_at": "2026-06-03T10:00:00Z"
}
```

**GET /journal**
```
Query params: q (title search, max 200 chars), limit (default 20, max 100), offset
```

---

### Journal Prompts

Authentication required.

| Method | Path                      | Description                                                    |
| ------ | ------------------------- | -------------------------------------------------------------- |
| GET    | `/journal/prompts/daily`  | Get today's deterministic reflective prompt for the user.      |
| GET    | `/journal/prompts/next`   | Get the next prompt after the currently displayed one.         |
| GET    | `/journal/prompts`        | List all prompts, optionally filtered by topic.                |

**GET /journal/prompts/daily — Response:**
```json
{
  "prompt": {
    "id": 12,
    "text": "What made you smile today?",
    "topic": "gratitude"
  },
  "topics": ["gratitude", "reflection", "growth", "relationships", "emotions"]
}
```

**GET /journal/prompts/next**
```
Query params: current_id (required) — ID of the prompt currently shown
```

**GET /journal/prompts**
```
Query params: topic (optional) — filter by topic slug
```

---

### Exercises

| Method | Path                       | Description                                                      |
| ------ | -------------------------- | ---------------------------------------------------------------- |
| GET    | `/exercises`               | List all exercises, optionally filtered by mood and/or category. (auth required) |
| GET    | `/exercises/recommended`   | Get top N exercises recommended for a given mood. (auth required) |
| GET    | `/exercises/categories`    | Get all exercise categories with display labels (public).         |
| GET    | `/exercises/mood-filters`  | Get all mood filter options with display labels (public).         |
| POST   | `/exercises/logs`          | Record a completed exercise session. (auth required)              |
| GET    | `/exercises/logs/history`  | Get the user's exercise completion history. (auth required)       |
| GET    | `/exercises/{slug}`        | Get full exercise detail including steps and phases. (auth required) |

**GET /exercises**
```
Query params: mood (optional), category (optional)
```

**Mood values:** `very_low` | `low` | `neutral` | `high` | `very_high`

**Category values:** `breathing` | `meditation` | `movement` | `cognitive` | `relaxation`

**GET /exercises/recommended**
```
Query params: mood (required), limit (default 3, max 10)
```

**POST /exercises/logs — Request body:**
```json
{ "exercise_slug": "breathing-4-7-8", "duration_seconds": 180, "completed_at": "2026-06-03T10:00:00Z" }
```

**GET /exercises/logs/history**
```
Query params: limit (default 20, max 100), offset
```

---

### Chat (AI Companion)

| Method | Path                                          | Description                                              |
| ------ | --------------------------------------------- | -------------------------------------------------------- |
| GET    | `/chat/quick-prompts`                         | Get suggested prompts for empty conversations (public).  |
| POST   | `/chat/conversations`                         | Create a new conversation thread. (auth required)        |
| GET    | `/chat/conversations`                         | List conversations with optional title search. (auth)    |
| DELETE | `/chat/conversations/{id}`                    | Delete a conversation and all its messages. (auth)       |
| GET    | `/chat/conversations/{id}/messages`           | Get all messages in a conversation. (auth required)      |
| POST   | `/chat/conversations/{id}/messages`           | Send a message and receive the AI response via SSE. (auth) |

**Note:** AI responses are streamed as Server-Sent Events (SSE).

**POST /chat/conversations — Request body:**
```json
{ "title": "Feeling anxious" }
```

**POST /chat/conversations/{id}/messages — Request body:**
```json
{ "content": "I've been feeling very stressed lately." }
```

**SSE Response format:**

The response is a stream with `Content-Type: text/event-stream`. Three event types:

```
data: {"type": "chunk", "content": "I hear you..."}

data: {"type": "done", "message_id": 42, "exercise_card": null, "sentiment": "negative", "suggest_checkin": false}

data: {"type": "error", "detail": "Service unavailable"}
```

- `exercise_card`: non-null when the AI suggests a breathing exercise. Contains the exercise object.
- `sentiment`: `"positive"` | `"neutral"` | `"negative"`
- `suggest_checkin`: `true` after 5 or more consecutive negative messages

---

### Thought Records (CBT)

Authentication required.

| Method | Path                      | Description                                                      |
| ------ | ------------------------- | ---------------------------------------------------------------- |
| GET    | `/thought-records/hints`  | Get placeholder hints for each of the 5 CBT columns.            |
| GET    | `/thought-records`        | List all thought records for the current user.                   |
| POST   | `/thought-records`        | Create a new CBT thought record.                                 |
| GET    | `/thought-records/{id}`   | Get a single thought record.                                     |
| PATCH  | `/thought-records/{id}`   | Update a thought record.                                         |
| DELETE | `/thought-records/{id}`   | Delete a thought record.                                         |

**The 5 CBT columns:**

| Column              | Description                                              |
| ------------------- | -------------------------------------------------------- |
| `situation`         | What happened? Where, when, who was involved?            |
| `automatic_thought` | What thought went through your mind?                     |
| `emotion`           | What emotion did you feel? Rate intensity 0-100.         |
| `evidence_for`      | Evidence that supports the thought.                      |
| `evidence_against`  | Evidence that challenges the thought.                    |

**POST /thought-records — Request body:**
```json
{
  "situation": "My boss criticized my report",
  "automatic_thought": "I'm incompetent",
  "emotion": "Shame — 80%",
  "evidence_for": "The report had errors",
  "evidence_against": "I've delivered good work before"
}
```

**GET /thought-records**
```
Query params: limit (default 20, max 100), offset
```

---

### Safety Plan

Authentication required.

| Method | Path            | Description                                                    |
| ------ | --------------- | -------------------------------------------------------------- |
| GET    | `/safety-plan`  | Get the current user's safety plan (404 if not yet created).   |
| PUT    | `/safety-plan`  | Create or replace the safety plan.                             |

**PUT /safety-plan — Request body (all fields optional):**
```json
{
  "warning_signs": ["Difficulty sleeping", "Withdrawing from friends"],
  "coping_activities": ["Deep breathing", "Call a friend", "Go for a walk"],
  "trusted_contacts": [
    { "name": "Nguyen Van B", "phone": "0901234567" }
  ],
  "reasons_to_live": "My family, my goals, my future..."
}
```

**Safety plan object:**
```json
{
  "id": 1,
  "warning_signs": ["Difficulty sleeping"],
  "coping_activities": ["Deep breathing"],
  "trusted_contacts": [{ "name": "Nguyen Van B", "phone": "0901234567" }],
  "reasons_to_live": "My family...",
  "updated_at": "2026-06-03T10:00:00Z"
}
```

---

### Crisis Resources

No authentication required. Always accessible without login.

| Method | Path                 | Description                                                   |
| ------ | -------------------- | ------------------------------------------------------------- |
| GET    | `/crisis/resources`  | Get crisis hotline numbers and an emergency breathing exercise. |

**Response:**
```json
{
  "message": "You are not alone. We are here with you.",
  "hotlines": [
    {
      "name": "Mental Health Support Line - Ministry of Health",
      "number": "1800 599 920",
      "description": "Free, 24/7, confidential",
      "available": "24/7"
    },
    {
      "name": "Emergency Line",
      "number": "113",
      "description": "Police — for immediate danger",
      "available": "24/7"
    }
  ],
  "breathing_exercise": {
    "exercise_slug": "breathing-4-7-8",
    "title": "4-7-8 Breathing",
    "description": "Inhale 4s, hold 7s, exhale 8s."
  }
}
```

---

### Dashboard

| Method | Path          | Description                                                             |
| ------ | ------------- | ----------------------------------------------------------------------- |
| GET    | `/dashboard`  | Get home dashboard: greeting, mood status, streak, sparkline, and tips. (auth required) |
| GET    | `/dashboard/quote` | Get today's motivational quote (rotates daily). (auth required)       |

**GET /dashboard — Response:**
```json
{
  "greeting": "Good morning, Nguyen Van A",
  "streak_days": 7,
  "today_checked_in": false,
  "last_mood": 4,
  "sparkline": [3, 4, 3, 5, 4, null, 4],
  "recommended_exercises": [...],
  "phq9_reminder": { "due": false }
}
```

**GET /dashboard/quote — Response:**
```json
{
  "quote": "The only way out is through.",
  "author": "Robert Frost"
}
```

---

### Resources

Authentication required.

| Method | Path                      | Description                                        |
| ------ | ------------------------- | -------------------------------------------------- |
| GET    | `/resources/recommended`  | Get a curated list of healing resources.           |

**GET /resources/recommended**
```
Query params: limit (default 2, max 10)
```

**Response:**
```json
[
  {
    "id": 1,
    "title": "Mindfulness for Beginners",
    "description": "Learn foundational mindfulness techniques...",
    "url": "https://example.com/mindfulness",
    "category": "meditation"
  }
]
```

---

### Community

No authentication required. Community features are publicly accessible.

| Method | Path                 | Description                                   |
| ------ | -------------------- | --------------------------------------------- |
| GET    | `/community/featured` | Get a featured community message.              |

**Response:**
```json
{
  "message": "You are not alone. Our community is here to support you.",
  "featured_date": "2026-06-07"
}
```

---

### Wellness

Authentication required.

| Method | Path                           | Description                                                  |
| ------ | ------------------------------ | ------------------------------------------------------------ |
| GET    | `/wellness/checklist`          | Get the daily wellness checklist with completion state.      |
| PUT    | `/wellness/checklist/{item_id}`| Mark a wellness checklist item as completed or not.          |

**GET /wellness/checklist**
```
Query params: date (optional, defaults to today in Vietnam timezone)
```

**Response:**
```json
{
  "date": "2026-06-07",
  "items": [
    {
      "id": "morning_mood",
      "label": "Check in on your mood",
      "completed": true
    }
  ]
}
```

**PUT /wellness/checklist/{item_id}**
```
Query params: date (optional, defaults to today)
Request body: { "completed": true }
```

---

### Badges

Authentication required.

| Method | Path       | Description                                                                   |
| ------ | ---------- | ----------------------------------------------------------------------------- |
| GET    | `/badges`  | Get streak count and badge status. Newly reached milestones are marked as seen. |

**Response:**
```json
{
  "streak_days": 7,
  "badges": [
    {
      "slug": "streak-7",
      "label": "7-day streak",
      "milestone_days": 7,
      "unlocked": true,
      "is_new": true
    },
    {
      "slug": "streak-30",
      "label": "30-day streak",
      "milestone_days": 30,
      "unlocked": false,
      "is_new": false
    }
  ]
}
```

`is_new` is `true` only on the first response after the milestone is reached. Use this flag to trigger a celebration animation.

---

### Notifications

Authentication required.

| Method | Path                             | Description                                                       |
| ------ | -------------------------------- | ----------------------------------------------------------------- |
| GET    | `/notifications/preference`      | Get notification preferences (created with defaults on first call). |
| PATCH  | `/notifications/preference`      | Update one or more notification preference fields.                |
| GET    | `/notifications/should-notify`   | Check whether to show a mood check-in reminder right now.         |
| GET    | `/notifications/exercise-reminder` | Check whether to show a daily exercise reminder right now.      |

**Notification preference object:**
```json
{
  "enabled": true,
  "reminder_time": "20:00",
  "quiet_start": "22:00",
  "quiet_end": "08:00",
  "exercise_enabled": true,
  "exercise_reminder_time": "09:00"
}
```

**PATCH /notifications/preference — All fields optional:**
```json
{
  "enabled": true,
  "reminder_time": "20:00",
  "quiet_start": "23:00",
  "quiet_end": "07:00",
  "exercise_enabled": false,
  "exercise_reminder_time": "09:00"
}
```

Time format: `HH:MM` (24-hour).

**GET /notifications/should-notify and /notifications/exercise-reminder — Response:**
```json
{ "should_notify": true, "reason": "Within reminder window and user has not checked in today" }
```

---

### Health Check

No authentication required.

| Method | Path       | Description                                       |
| ------ | ---------- | ------------------------------------------------- |
| GET    | `/health`  | Check app and database connectivity.              |

**Response 200:**
```json
{ "status": "ok", "db": "connected" }
```

**Response 503:** Database unreachable.

---

## Authentication Guide

All protected endpoints require a Bearer token in the `Authorization` header:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Login flow:**
1. `POST /auth/register` — create account
2. User clicks verification link in email (`GET /auth/verify?token=...`)
3. `POST /auth/login` — get access token
4. Include token in all subsequent requests

**Google OAuth flow:**
1. `GET /auth/google` — get `authorization_url`
2. Redirect user to `authorization_url`
3. Google redirects to callback with `?code=...`
4. `GET /auth/google/callback?code=...` — get access token

---

## Streaming Chat Guide

The chat message endpoint uses Server-Sent Events (SSE). The frontend must handle three event types:

```javascript
const response = await fetch('/api/v1/chat/conversations/1/messages', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({ content: 'Hello' }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  const text = decoder.decode(value);
  const lines = text.split('\n').filter(line => line.startsWith('data: '));

  for (const line of lines) {
    const event = JSON.parse(line.replace('data: ', ''));

    if (event.type === 'chunk') {
      // Append event.content to the message bubble
    } else if (event.type === 'done') {
      // Streaming complete
      // event.exercise_card — show exercise card if non-null
      // event.suggest_checkin — prompt mood check-in if true
      // event.sentiment — "positive" | "neutral" | "negative"
    } else if (event.type === 'error') {
      // Show error message
    }
  }
}
```

---

## Running Tests

```bash
pytest
pytest tests/test_journal.py -v   # run specific test file
pytest --cov=app                  # with coverage
```
