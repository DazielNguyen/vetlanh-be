from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.journal import JournalEntryCreate, JournalEntryResponse, JournalEntryUpdate
from app.services.journal import create_entry, delete_entry, get_entry, list_entries, update_entry

router = APIRouter(prefix="/journal", tags=["journal"])

_NOT_FOUND = "Journal entry not found"


@router.post("", response_model=JournalEntryResponse, status_code=201)
async def create_journal_entry(
    payload: JournalEntryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_entry(db, current_user.id, payload)


@router.get("", response_model=list[JournalEntryResponse])
async def list_journal_entries(
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_entries(db, current_user.id, q=q, limit=limit, offset=offset)


@router.get("/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = await get_entry(db, current_user.id, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return entry


@router.patch("/{entry_id}", response_model=JournalEntryResponse)
async def update_journal_entry(
    entry_id: int,
    payload: JournalEntryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = await update_entry(db, current_user.id, entry_id, payload)
    if entry is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return entry


@router.delete("/{entry_id}", status_code=204, response_model=None)
async def delete_journal_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await delete_entry(db, current_user.id, entry_id):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
