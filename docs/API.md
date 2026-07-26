 Here's a full explanation of all the APIs in this project:
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  What is an API?
  
  API (Application Programming Interface) is a set of rules and endpoints that allows a frontend app (mobile/web) to communicate with the backend server. In this project, APIs are HTTP
  endpoints — the frontend sends HTTP requests (GET, POST, PATCH, PUT, DELETE) to specific URLs, and the server responds with JSON data.
  
  The project uses FastAPI (Python framework) which automatically handles request validation, serialization, and generates interactive docs at /docs.
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  How the APIs work (Architecture)
  
  Frontend (React/Flutter)
      ↓ HTTP Request (with JWT token)
      ↓
  FastAPI Router (app/api/v1/endpoints/*.py)
      ↓ Validates input, checks auth
      ↓
  Service Layer (app/services/*.py)
      ↓ Business logic
      ↓
  Database (PostgreSQL via SQLAlchemy async)
      ↓
  Response → JSON back to frontend
  
  Key patterns:
  
  1. Authentication: Most endpoints require a JWT Bearer token in the Authorization header. The get_current_user dependency validates the token and injects the current user.
  2. Database sessions: get_db dependency provides an async SQLAlchemy session that auto-commits on success and rolls back on error.
  3. Base URL: All endpoints are prefixed with /api/v1/.
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  All APIs in this project
  
  1. Health Check (health.py)
  
  ┌─────────────┬─────────────────────────────────────────────┐
  │ Endpoint    │ Description                                 │
  ├─────────────┼─────────────────────────────────────────────┤
  │ GET /health │ Check if the app and database are connected │
  └─────────────┴─────────────────────────────────────────────┘
  
  No auth needed. Returns {"status": "ok", "db": "connected"}.
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  2. Authentication (auth.py)
  
  ┌────────────────────────────────┬──────────────────────────────────────────────────────────┐
  │ Endpoint                       │ Description                                              │
  ├────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ POST /auth/register            │ Register with email + password, sends verification email │
  ├────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ POST /auth/register-username   │ Register with username + password (no email)             │
  ├────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ POST /auth/login               │ Login with email, returns JWT token                      │
  ├────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ POST /auth/login-username      │ Login with username, returns JWT token                   │
  ├────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ GET /auth/verify?token=...     │ Verify email from link                                   │
  ├────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ POST /auth/resend-verification │ Resend email verification link                           │
  └────────────────────────────────┴──────────────────────────────────────────────────────────┘
  
  How it works: User registers → gets a JWT token → includes it in all future requests.
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  3. Users / Profile (users.py)
  
  ┌───────────────────────────────┬──────────────────────────────────────────────────┐
  │ Endpoint                      │ Description                                      │
  ├───────────────────────────────┼──────────────────────────────────────────────────┤
  │ GET /users/me                 │ Get current user profile (+ subscription status) │
  ├───────────────────────────────┼──────────────────────────────────────────────────┤
  │ PATCH /users/me               │ Update display name, avatar, timezone            │
  ├───────────────────────────────┼──────────────────────────────────────────────────┤
  │ PUT /users/me/goals           │ Set wellness goals                               │
  ├───────────────────────────────┼──────────────────────────────────────────────────┤
  │ GET /users/me/goals/available │ List all goal options                            │
  ├───────────────────────────────┼──────────────────────────────────────────────────┤
  │ GET /users/me/mood-summary    │ Sparse mood entries for last N days              │
  ├───────────────────────────────┼──────────────────────────────────────────────────┤
  │ GET /users/me/stats           │ Exercises completed, mood streak                 │
  ├───────────────────────────────┼──────────────────────────────────────────────────┤
  │ GET /users/me/healing-path    │ Progress across self-care tasks                  │
  └───────────────────────────────┴──────────────────────────────────────────────────┘
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  4. PHQ-9 Assessments (assessments.py)
  
  ┌─────────────────────────────────┬───────────────────────────────────────────────────┐
  │ Endpoint                        │ Description                                       │
  ├─────────────────────────────────┼───────────────────────────────────────────────────┤
  │ GET /assessments/phq9/questions │ Get the 9 depression screening questions (public) │
  ├─────────────────────────────────┼───────────────────────────────────────────────────┤
  │ POST /assessments/phq9          │ Submit answers (9 values, each 0-3)               │
  ├─────────────────────────────────┼───────────────────────────────────────────────────┤
  │ GET /assessments/phq9/latest    │ Get most recent result                            │
  ├─────────────────────────────────┼───────────────────────────────────────────────────┤
  │ GET /assessments/phq9/history   │ Paginated history with score deltas               │
  ├─────────────────────────────────┼───────────────────────────────────────────────────┤
  │ GET /assessments/phq9/reminder  │ Check if reassessment is due (14-day cycle)       │
  └─────────────────────────────────┴───────────────────────────────────────────────────┘
  
  How it works: User answers 9 questions → server calculates score (0-27) → assigns severity level (minimal/mild/moderate/moderately_severe/severe) → suggests wellness goals.
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  5. Mood Tracking (mood.py)
  
  ┌────────────────────┬────────────────────────────────────────────┐
  │ Endpoint           │ Description                                │
  ├────────────────────┼────────────────────────────────────────────┤
  │ POST /mood/entries │ Log mood (1-5), energy, factors for a date │
  ├────────────────────┼────────────────────────────────────────────┤
  │ GET /mood/entries  │ List entries with date range filter        │
  ├────────────────────┼────────────────────────────────────────────┤
  │ GET /mood/insights │ AI-generated insights (needs 7+ check-ins) │
  ├────────────────────┼────────────────────────────────────────────┤
  │ GET /mood/heatmap  │ Calendar heatmap for a month               │
  ├────────────────────┼────────────────────────────────────────────┤
  │ GET /mood/trend    │ Trend data for last 7 or 30 days           │
  ├────────────────────┼────────────────────────────────────────────┤
  │ GET /mood/factors  │ List of available factors (public)         │
  └────────────────────┴────────────────────────────────────────────┘
  
  How it works: One mood entry per day. Can update within 1 hour; after that, it's locked (409 Conflict).
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  6. Journal (journal.py)
  
  ┌──────────────────────┬────────────────────────────────┐
  │ Endpoint             │ Description                    │
  ├──────────────────────┼────────────────────────────────┤
  │ POST /journal        │ Create entry (title + content) │
  ├──────────────────────┼────────────────────────────────┤
  │ GET /journal         │ List entries with title search │
  ├──────────────────────┼────────────────────────────────┤
  │ GET /journal/{id}    │ Get single entry               │
  ├──────────────────────┼────────────────────────────────┤
  │ PATCH /journal/{id}  │ Update entry                   │
  ├──────────────────────┼────────────────────────────────┤
  │ DELETE /journal/{id} │ Delete entry                   │
  └──────────────────────┴────────────────────────────────┘
  
  How it works: Content is encrypted at rest using Fernet encryption. Decrypted only when the owner requests it.
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  7. Journal Prompts (journal_prompts.py)
  
  ┌────────────────────────────┬───────────────────────────────────────────┐
  │ Endpoint                   │ Description                               │
  ├────────────────────────────┼───────────────────────────────────────────┤
  │ GET /journal/prompts/daily │ Today's reflective writing prompt         │
  ├────────────────────────────┼───────────────────────────────────────────┤
  │ GET /journal/prompts/next  │ Next prompt after current one             │
  ├────────────────────────────┼───────────────────────────────────────────┤
  │ GET /journal/prompts       │ All prompts, optionally filtered by topic │
  └────────────────────────────┴───────────────────────────────────────────┘
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  8. Exercises (exercises.py)
  
  ┌────────────────────────────────┬──────────────────────────────────────────────┐
  │ Endpoint                       │ Description                                  │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ GET /exercises                 │ List all exercises (filter by mood/category) │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ GET /exercises/recommended     │ Top N for a given mood                       │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ GET /exercises/{slug}          │ Full exercise detail (steps, phases, audio)  │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ POST /exercises/logs           │ Record a completed session                   │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ PATCH /exercises/logs/{id}     │ Record post-session feeling                  │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ GET /exercises/logs/history    │ Completion history                           │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ GET /exercises/categories      │ All categories (public)                      │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ GET /exercises/mood-filters    │ Mood filter options (public)                 │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ GET /exercises/feeling-options │ Post-session feeling options (public)        │
  └────────────────────────────────┴──────────────────────────────────────────────┘
  
  Categories: breathing, meditation, movement, cognitive, relaxation.
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  9. AI Chat (chat.py)
  
  ┌────────────────────────────────────────┬───────────────────────────────────────────────┐
  │ Endpoint                               │ Description                                   │
  ├────────────────────────────────────────┼───────────────────────────────────────────────┤
  │ GET /chat/quick-prompts                │ Suggested conversation starters (public)      │
  ├────────────────────────────────────────┼───────────────────────────────────────────────┤
  │ POST /chat/conversations               │ Create a new conversation                     │
  ├────────────────────────────────────────┼───────────────────────────────────────────────┤
  │ GET /chat/conversations                │ List conversations (with search)              │
  ├────────────────────────────────────────┼───────────────────────────────────────────────┤
  │ DELETE /chat/conversations/{id}        │ Delete a conversation                         │
  ├────────────────────────────────────────┼───────────────────────────────────────────────┤
  │ GET /chat/conversations/{id}/messages  │ Get all messages                              │
  ├────────────────────────────────────────┼───────────────────────────────────────────────┤
  │ POST /chat/conversations/{id}/messages │ Send message → get AI response via SSE stream │
  └────────────────────────────────────────┴───────────────────────────────────────────────┘
  
  How it works: The AI companion uses OpenAI Responses API. Responses are streamed as Server-Sent Events (SSE) — the frontend receives tokens one-by-one for a typing effect. It also detects
  sentiment and suggests mood check-ins after 5+ negative messages.
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  10. Thought Records - CBT (thought_records.py)
  
  ┌──────────────────────────────┬─────────────────────────────────────────┐
  │ Endpoint                     │ Description                             │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ GET /thought-records/hints   │ Placeholder hints for the 5 CBT columns │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ GET /thought-records         │ List all records                        │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ POST /thought-records        │ Create a CBT record                     │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ GET /thought-records/{id}    │ Get one                                 │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ PATCH /thought-records/{id}  │ Update                                  │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ DELETE /thought-records/{id} │ Delete                                  │
  └──────────────────────────────┴─────────────────────────────────────────┘
  
  How it works: Structured cognitive behavioral therapy tool — user fills in situation, automatic thought, emotion, evidence for, evidence against.
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  11. Safety Plan (safety_plan.py)
  
  ┌──────────────────┬───────────────────────────────┐
  │ Endpoint         │ Description                   │
  ├──────────────────┼───────────────────────────────┤
  │ GET /safety-plan │ Get user's safety plan        │
  ├──────────────────┼───────────────────────────────┤
  │ PUT /safety-plan │ Create or replace safety plan │
  └──────────────────┴───────────────────────────────┘
  
  Contains: warning signs, coping activities, trusted contacts, reasons to live.
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  12. Crisis Resources (crisis.py)
  
  ┌───────────────────────┬──────────────────────────────────────────────────┐
  │ Endpoint              │ Description                                      │
  ├───────────────────────┼──────────────────────────────────────────────────┤
  │ GET /crisis/resources │ Hotlines + emergency breathing exercise (public) │
  └───────────────────────┴──────────────────────────────────────────────────┘
  
  Always accessible without login. Returns Vietnam crisis hotlines.
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  13. Dashboard (dashboard.py)
  
  ┌──────────────────────┬─────────────────────────────────────────────────────────────────┐
  │ Endpoint             │ Description                                                     │
  ├──────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ GET /dashboard       │ Home screen data (greeting, streak, sparkline, recommendations) │
  ├──────────────────────┼─────────────────────────────────────────────────────────────────┤
  │ GET /dashboard/quote │ Daily motivational quote                                        │
  └──────────────────────┴─────────────────────────────────────────────────────────────────┘
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  14. Badges (badges.py)
  
  ┌─────────────┬────────────────────────────────────────────────────┐
  │ Endpoint    │ Description                                        │
  ├─────────────┼────────────────────────────────────────────────────┤
  │ GET /badges │ Streak count + badge milestones (7, 30 days, etc.) │
  └─────────────┴────────────────────────────────────────────────────┘
  
  Marks newly unlocked badges with is_new: true for celebration animations.
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  15. Notifications (notifications.py)
  
  ┌──────────────────────────────────────┬──────────────────────────────────────┐
  │ Endpoint                             │ Description                          │
  ├──────────────────────────────────────┼──────────────────────────────────────┤
  │ GET /notifications/preference        │ Get notification settings            │
  ├──────────────────────────────────────┼──────────────────────────────────────┤
  │ PATCH /notifications/preference      │ Update settings (times, quiet hours) │
  ├──────────────────────────────────────┼──────────────────────────────────────┤
  │ GET /notifications/should-notify     │ Should show mood reminder now?       │
  ├──────────────────────────────────────┼──────────────────────────────────────┤
  │ GET /notifications/exercise-reminder │ Should show exercise reminder now?   │
  └──────────────────────────────────────┴──────────────────────────────────────┘
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  16. Resources (resources.py)
  
  ┌────────────────────────────┬─────────────────────────────────────────────┐
  │ Endpoint                   │ Description                                 │
  ├────────────────────────────┼─────────────────────────────────────────────┤
  │ GET /resources/recommended │ Curated healing resources (articles, links) │
  └────────────────────────────┴─────────────────────────────────────────────┘
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  17. Community (community.py)
  
  ┌─────────────────────────┬─────────────────────────────────────┐
  │ Endpoint                │ Description                         │
  ├─────────────────────────┼─────────────────────────────────────┤
  │ GET /community/featured │ Featured community message (public) │
  └─────────────────────────┴─────────────────────────────────────┘
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  18. Wellness Checklist (wellness.py)
  
  ┌───────────────────────────────────┬───────────────────────────────────────┐
  │ Endpoint                          │ Description                           │
  ├───────────────────────────────────┼───────────────────────────────────────┤
  │ GET /wellness/checklist           │ Daily checklist with completion state │
  ├───────────────────────────────────┼───────────────────────────────────────┤
  │ PUT /wellness/checklist/{item_id} │ Mark item as done/undone              │
  └───────────────────────────────────┴───────────────────────────────────────┘
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  19. Sounds (sounds.py)
  
  ┌──────────────────────────────┬──────────────────────────────────────┐
  │ Endpoint                     │ Description                          │
  ├──────────────────────────────┼──────────────────────────────────────┤
  │ GET /sounds                  │ List all published ambient sounds    │
  ├──────────────────────────────┼──────────────────────────────────────┤
  │ GET /sounds/{id}             │ Get single sound                     │
  ├──────────────────────────────┼──────────────────────────────────────┤
  │ POST /sounds                 │ Create sound (admin only)            │
  ├──────────────────────────────┼──────────────────────────────────────┤
  │ POST /sounds/{id}/upload-url │ Get Cloudinary upload params (admin) │
  ├──────────────────────────────┼──────────────────────────────────────┤
  │ POST /sounds/{id}/upload     │ Upload audio file (admin)            │
  ├──────────────────────────────┼──────────────────────────────────────┤
  │ PATCH /sounds/{id}           │ Update sound (admin)                 │
  ├──────────────────────────────┼──────────────────────────────────────┤
  │ DELETE /sounds/{id}          │ Delete sound (admin)                 │
  └──────────────────────────────┴──────────────────────────────────────┘
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  20. Articles (articles.py)
  
  ┌────────────────────────────────┬──────────────────────────────────────────────┐
  │ Endpoint                       │ Description                                  │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ GET /articles                  │ List published articles (filter by category) │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ GET /articles/{id}             │ Get single article                           │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ POST /articles                 │ Create article (admin)                       │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ PATCH /articles/{id}           │ Update article (admin)                       │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ POST /articles/{id}/upload-url │ Cloudinary upload params (admin)             │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ DELETE /articles/{id}          │ Delete article (admin)                       │
  └────────────────────────────────┴──────────────────────────────────────────────┘
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  21. Subscriptions (subscriptions.py)
  
  ┌────────────────────────────────────┬─────────────────────────────────────┐
  │ Endpoint                           │ Description                         │
  ├────────────────────────────────────┼─────────────────────────────────────┤
  │ POST /subscriptions/pending        │ Submit a subscription request       │
  ├────────────────────────────────────┼─────────────────────────────────────┤
  │ POST /subscriptions/payment-notify │ Upload payment bill + notify admins │
  └────────────────────────────────────┴─────────────────────────────────────┘
  
  How it works: User pays → uploads bill screenshot → admin reviews and approves via admin panel.
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  22. Error Reporting (errors.py)
  
  ┌─────────────────────┬────────────────────────────────────────────────────────────┐
  │ Endpoint            │ Description                                                │
  ├─────────────────────┼────────────────────────────────────────────────────────────┤
  │ POST /errors/report │ Frontend reports client-side errors (rate-limited: 10/min) │
  └─────────────────────┴────────────────────────────────────────────────────────────┘
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  23. Admin Panel (admin/)
  
  ┌────────────────────────────────┬──────────────────────────────────────┐
  │ Endpoint                       │ Description                          │
  ├────────────────────────────────┼──────────────────────────────────────┤
  │ GET/PATCH /admin/users         │ Manage users                         │
  ├────────────────────────────────┼──────────────────────────────────────┤
  │ GET/PATCH /admin/subscriptions │ Approve/reject subscription requests │
  ├────────────────────────────────┼──────────────────────────────────────┤
  │ GET /admin/stats               │ System statistics                    │
  ├────────────────────────────────┼──────────────────────────────────────┤
  │ GET /admin/errors              │ View reported errors                 │
  └────────────────────────────────┴──────────────────────────────────────┘
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  24. WebSocket Hub (hub.py)
  
  ┌──────────────────────────┬───────────────────────────────────────────────────┐
  │ Endpoint                 │ Description                                       │
  ├──────────────────────────┼───────────────────────────────────────────────────┤
  │ POST /hubs/app/negotiate │ Get one-time WebSocket ticket                     │
  ├──────────────────────────┼───────────────────────────────────────────────────┤
  │ WS /hubs/app?id=<ticket> │ Real-time WebSocket connection (SignalR protocol) │
  └──────────────────────────┴───────────────────────────────────────────────────┘
  
  How it works: Uses SignalR-compatible protocol. The server can push real-time notifications to connected clients via send_to_user().
  
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  Summary
  
  The project has ~80+ API endpoints organized across 24 modules, covering:
  
  - Authentication (JWT + Google OAuth + username-based)
  - Mental health tools (PHQ-9, mood tracking, CBT thought records, safety plan)
  - Wellness features (exercises, journal, daily checklist, badges/streaks)
  - AI companion (streamed chat via OpenAI Responses API)
  - Content management (articles, sounds, resources)
  - Real-time (WebSocket notifications)
  - Admin (user management, subscription approval, error monitoring)
