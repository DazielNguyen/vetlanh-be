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

    # OpenAI — required for AI chat and mood reflection; startup fails loudly when missing
    OPENAI_API_KEY: str
    # Override these in deployment when a different cost/quality tier is preferred.
    OPENAI_CHAT_MODEL: str = "gpt-5.6-terra"
    OPENAI_MOOD_MODEL: str = "gpt-5.6-luna"

    FRONTEND_URL: str = "http://localhost:5173"

    # Single origin used to build frontend links in emails (verification, password reset).
    # Set to the canonical public URL, e.g. https://vetlanh.io.vn
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # Extra comma-separated origins to allow in addition to FRONTEND_URL and localhost defaults.
    # Example: CORS_ORIGINS=https://vetlanh.io.vn,https://www.vetlanh.io.vn
    CORS_ORIGINS: str = ""

    # Comma-separated list of usernames or emails allowed to access admin endpoints.
    ADMIN_USERS: str = ""

    # Comma-separated email(s) to notify when a new payment bill is submitted.
    ADMIN_NOTIFICATION_EMAILS: str = "duynguyenvananh@gmail.com"

    # Directory for storing uploaded files (bill images). Relative to project root.
    UPLOADS_DIR: str = "uploads"

    # Cloudinary — image and audio storage; no default so startup fails loudly when missing
    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str

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
