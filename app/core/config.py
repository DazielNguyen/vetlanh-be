from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Email — Resend API used for verification emails
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "noreply@vetlanh.io.vn"

    # Public origin of the API server — used to build email verification links.
    # Must always point at the backend (e.g. https://api.vetlanh.io.vn), never the frontend.
    APP_BASE_URL: str = "http://localhost:8000"

    # Journal encryption — required; no default so startup fails loudly when missing
    JOURNAL_ENCRYPTION_KEY: str

    # Groq — required for AI chat; no default so startup fails loudly when missing
    GROQ_API_KEY: str

    # Google OAuth2 — required only when Google login is enabled
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"
    FRONTEND_URL: str = "http://localhost:5173"

    # Extra comma-separated origins to allow in addition to FRONTEND_URL and localhost defaults.
    # Example: CORS_ORIGINS=https://vetlanh.io.vn,https://www.vetlanh.io.vn
    CORS_ORIGINS: str = ""

    # Comma-separated list of usernames or emails allowed to access admin endpoints.
    ADMIN_USERS: str = ""

    # Comma-separated email(s) to notify when a new payment bill is submitted.
    ADMIN_NOTIFICATION_EMAILS: str = "duynguyenvananh@gmail.com"

    # Directory for storing uploaded files (bill images). Relative to project root.
    UPLOADS_DIR: str = "uploads"

    # Base URL used to construct audio_url in SoundResponse.
    # Production: https://api.vetlanh.app  (Nginx serves /media/sounds/ directly)
    # Local dev: http://localhost:8000     (FastAPI StaticFiles mount)
    MEDIA_BASE_URL: str = "http://localhost:8000"

    # Filesystem path to the sounds directory (used by StaticFiles in local dev).
    SOUNDS_DIR: str = "media/sounds"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        # .env also contains POSTGRES_* vars consumed by Docker Compose, not this app.
        # "ignore" prevents ValidationError on those unknown fields.
        extra="ignore",
    )


# Module-level instantiation: raises ValidationError immediately at startup
# if DATABASE_URL or SECRET_KEY is missing — not silently on first request.
settings = Settings()
