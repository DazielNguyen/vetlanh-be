from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

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
