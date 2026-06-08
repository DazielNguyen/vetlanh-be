from fastapi import APIRouter

from app.api.v1.endpoints.admin import errors, stats, subscriptions, users

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(stats.router)
router.include_router(users.router)
router.include_router(subscriptions.router)
router.include_router(errors.router)
