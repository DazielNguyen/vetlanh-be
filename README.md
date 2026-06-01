# vetlanh-be

FastAPI backend with async PostgreSQL.

## Requirements

- Python 3.11+
- Docker & Docker Compose

## Setup

```bash
# 1. Clone and enter project
git clone <repo-url>
cd vetlanh-be

# 2. Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment file
cp .env.example .env
# Edit .env and set SECRET_KEY to a random value

# 5. Start PostgreSQL
docker compose up -d --wait

# 6. Run database migrations
alembic upgrade head

# 7. Start the app
uvicorn app.main:app --reload
```

## API

- `GET  /api/v1/health`          — health check (DB connectivity)
- `POST /api/v1/auth/register`   — register a new user
- `POST /api/v1/auth/login`      — login, returns JWT token
- `GET  /api/v1/users/me`        — get current user (requires Bearer token)
- `POST /api/v1/journal`         — create journal entry (requires Bearer token)
- `GET  /api/v1/journal`         — list journal entries, supports ?q= keyword search (requires Bearer token)
- `GET  /api/v1/journal/{id}`    — get single journal entry (requires Bearer token)
- `PATCH /api/v1/journal/{id}`   — update journal entry (requires Bearer token)
- `DELETE /api/v1/journal/{id}`  — delete journal entry (requires Bearer token)
- `POST /api/v1/chat/conversations`       — create conversation (requires Bearer token)
- `GET  /api/v1/chat/conversations`       — list conversations, supports ?q= keyword search (requires Bearer token)
- `DELETE /api/v1/chat/conversations/{id}` — delete conversation (requires Bearer token)
- `GET  /api/v1/chat/conversations/{id}/messages` — list messages in conversation (requires Bearer token)
- `POST /api/v1/chat/conversations/{id}/messages` — send message and stream AI response (requires Bearer token)
- `POST /api/v1/mood/entries`      — create or update mood check-in (requires Bearer token)
- `GET  /api/v1/mood/entries`      — list mood entries, optional date range filter (requires Bearer token)
- `GET  /api/v1/mood/insights`     — get mood insights (requires at least 7 check-ins; requires Bearer token)
- `GET  /api/v1/mood/trend`        — get mood trend data for week or month (requires Bearer token)

Interactive docs: http://localhost:8000/docs
