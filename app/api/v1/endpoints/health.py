from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db

router = APIRouter()


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Check both app and database connectivity.
    Returns 200 if DB is reachable, 503 if not.
    """
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception:
        # 503 Service Unavailable — DB unreachable is an expected failure mode,
        # not a bug. Use 503, not 500.
        raise HTTPException(status_code=503, detail="Database unavailable")
