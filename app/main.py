import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.hub import router as hub_router
from app.api.v1 import router as v1_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.core.rate_limit import limiter
from app.core.seed import run_seed

logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    # Runs synchronously in a thread — Alembic uses psycopg2, not asyncpg.
    # Absolute path so this works regardless of cwd (dev, Docker, systemd, etc.)
    alembic_ini = Path(__file__).parent.parent / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini))
    command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Skip auto-migration on Vercel serverless — run `alembic upgrade head` manually
    # via Vercel CLI or a one-off script before deploying.
    if not os.getenv("VERCEL"):
        await asyncio.to_thread(_run_migrations)
        await run_seed()
    yield
    # dispose() drains the pool and closes all connections.
    # Skipping this causes "Event loop closed" / "unclosed connection" warnings.
    await engine.dispose()


app = FastAPI(title="vetlanh-be", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_cors_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    settings.FRONTEND_URL,
    *[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(_cors_origins)),  # deduplicate, preserve order
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Use a fresh session — the request session may be in a broken state.
    # Import here to avoid circular imports at module load time.
    from app.models.system_error import SystemError  # noqa: PLC0415

    try:
        async with AsyncSessionLocal() as db:
            db.add(
                SystemError(
                    error_type=type(exc).__name__,
                    route=str(request.url.path),
                    severity="HIGH",
                    description=str(exc)[:2000],
                    status="open",
                    timestamp=datetime.now(tz=timezone.utc),
                )
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to persist unhandled exception to system_errors")

    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(hub_router)
app.include_router(v1_router, prefix="/api/v1")

# Vercel serverless filesystem is read-only — skip local file serving.
# Uploads are routed to /tmp on Vercel (writable, but ephemeral per invocation).
if not os.getenv("VERCEL"):
    _uploads_path = Path(settings.UPLOADS_DIR)
    _uploads_path.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(_uploads_path)), name="uploads")

