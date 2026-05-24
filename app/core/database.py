from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    # expire_on_commit=False: accessing attributes after commit() would trigger a
    # lazy-load that raises MissingGreenlet in async context — disable it.
    expire_on_commit=False,
)
