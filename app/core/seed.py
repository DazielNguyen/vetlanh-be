"""
Dev seed — creates default accounts on first startup if they don't exist.
Idempotent: safe to run on every boot (skips if already present).

Accounts created:
  admin  username=duy1       password=Admin1234!   (in ADMIN_USERS whitelist)
  user   username=user_demo  password=User1234!
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401 — registers all models so SQLAlchemy resolves relationships
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User

logger = logging.getLogger(__name__)

_SEED_USERS = [
    {
        "username": "duy1",
        "display_name": "Admin",
        "raw_password": "Admin1234!",
        "account_type": "username",
    },
    {
        "username": "user_demo",
        "display_name": "Demo User",
        "raw_password": "User1234!",
        "account_type": "username",
    },
]


async def _upsert_user(db: AsyncSession, spec: dict) -> bool:
    result = await db.execute(select(User).where(User.username == spec["username"]))
    if result.scalar_one_or_none():
        return False  # already exists

    db.add(
        User(
            username=spec["username"],
            display_name=spec["display_name"],
            hashed_password=hash_password(spec["raw_password"]),
            is_active=True,
            is_verified=True,
            account_type=spec["account_type"],
        )
    )
    return True


async def run_seed() -> None:
    async with AsyncSessionLocal() as db:
        created = []
        for spec in _SEED_USERS:
            if await _upsert_user(db, spec):
                created.append(spec["username"])
        if created:
            await db.commit()
            logger.info("Seed: created users %s", created)
        else:
            logger.info("Seed: all seed users already exist, skipping")
