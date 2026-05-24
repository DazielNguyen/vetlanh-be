from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import router as v1_router
from app.core.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # dispose() drains the pool and closes all connections.
    # Skipping this causes "Event loop closed" / "unclosed connection" warnings.
    await engine.dispose()


app = FastAPI(title="vetlanh-be", lifespan=lifespan)
app.include_router(v1_router, prefix="/api/v1")
