import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.database import engine


def _run_migrations() -> None:
    # Runs synchronously in a thread — Alembic uses psycopg2, not asyncpg.
    # Absolute path so this works regardless of cwd (dev, Docker, systemd, etc.)
    alembic_ini = Path(__file__).parent.parent / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini))
    command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(_run_migrations)
    yield
    # dispose() drains the pool and closes all connections.
    # Skipping this causes "Event loop closed" / "unclosed connection" warnings.
    await engine.dispose()


app = FastAPI(title="vetlanh-be", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")
