from fastapi import APIRouter

from app.api.v1.endpoints.admin import analytics, community, errors, feedback, stats, subscriptions, users

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(stats.router)
router.include_router(users.router)
router.include_router(subscriptions.router)
router.include_router(errors.router)
router.include_router(feedback.router)
router.include_router(community.router)
router.include_router(analytics.router)
