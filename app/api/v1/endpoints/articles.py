import time
from datetime import datetime, timezone
from typing import Optional

import cloudinary.utils
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, get_db, require_admin
from app.models.article import Article
from app.schemas.article import VALID_CATEGORIES, ArticleCreate, ArticleResponse, ArticleUpdate
from app.schemas.sounds import CloudinaryUploadParams

router = APIRouter(prefix="/articles", tags=["articles"])


def _validate_category(category: str) -> None:
    if category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid category. Must be one of: {sorted(VALID_CATEGORIES)}",
        )


@router.get("", response_model=list[ArticleResponse])
async def list_articles(
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(Article).where(Article.is_published.is_(True))
    if category:
        stmt = stmt.where(Article.category == category)
    stmt = stmt.order_by(Article.sort_order.asc(), Article.published_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article(
    article_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.post("", response_model=ArticleResponse, status_code=201)
async def create_article(
    payload: ArticleCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    _validate_category(payload.category)
    existing = await db.get(Article, payload.id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Article ID already exists")

    article = Article(**payload.model_dump())
    if article.is_published and not article.published_at:
        article.published_at = datetime.now(timezone.utc)
    db.add(article)
    await db.flush()
    await db.refresh(article)
    return article


@router.patch("/{article_id}", response_model=ArticleResponse)
async def update_article(
    article_id: str,
    payload: ArticleUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    if payload.category is not None:
        _validate_category(payload.category)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(article, field, value)

    if article.is_published and not article.published_at:
        article.published_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(article)
    return article


@router.post("/{article_id}/upload-url", response_model=CloudinaryUploadParams)
async def get_article_upload_url(
    article_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    timestamp = int(time.time())
    folder = "vetlanh/articles"
    signature = cloudinary.utils.api_sign_request(
        {"folder": folder, "timestamp": timestamp},
        settings.CLOUDINARY_API_SECRET,
    )
    return CloudinaryUploadParams(
        upload_url=f"https://api.cloudinary.com/v1_1/{settings.CLOUDINARY_CLOUD_NAME}/image/upload",
        api_key=settings.CLOUDINARY_API_KEY,
        timestamp=timestamp,
        signature=signature,
        folder=folder,
    )


@router.delete("/{article_id}", status_code=204)
async def delete_article(
    article_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    await db.delete(article)
