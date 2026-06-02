"""CBT Thought Record endpoints — US-019."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.thought_record import (
    COLUMN_HINTS,
    ThoughtRecordCreate,
    ThoughtRecordHints,
    ThoughtRecordResponse,
    ThoughtRecordUpdate,
)
from app.services.thought_record import (
    create_record,
    delete_record,
    get_record,
    list_records,
    update_record,
)

router = APIRouter(prefix="/thought-records", tags=["thought-records"])

_NOT_FOUND = "Thought record not found"


@router.get("/hints", response_model=ThoughtRecordHints)
async def get_column_hints(_: User = Depends(get_current_user)):
    """US-019: Return placeholder hints for each of the 5 CBT columns."""
    return ThoughtRecordHints(**COLUMN_HINTS)


@router.get("", response_model=list[ThoughtRecordResponse])
async def list_thought_records(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_records(db, current_user.id, limit=limit, offset=offset)


@router.post("", response_model=ThoughtRecordResponse, status_code=201)
async def create_thought_record(
    payload: ThoughtRecordCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_record(db, current_user.id, payload)


@router.get("/{record_id}", response_model=ThoughtRecordResponse)
async def get_thought_record(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = await get_record(db, current_user.id, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return record


@router.patch("/{record_id}", response_model=ThoughtRecordResponse)
async def update_thought_record(
    record_id: int,
    payload: ThoughtRecordUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = await update_record(db, current_user.id, record_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return record


@router.delete("/{record_id}", status_code=204)
async def delete_thought_record(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await delete_record(db, current_user.id, record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
