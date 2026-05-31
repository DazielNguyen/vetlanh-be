from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Email / SMTP — used for verification emails
    SMTP_HOST: str = "sandbox.smtp.mailtrap.io"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@vetlanh.app"

    # Base URL used in email links (set to frontend URL in prod)
    APP_BASE_URL: str = "http://localhost:8000"

    # Anthropic — required for AI chat (Epic E2)
    ANTHROPIC_API_KEY: str = ""

    # Google OAuth2 — required only when Google login is enabled
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

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
