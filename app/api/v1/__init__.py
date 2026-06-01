from fastapi import APIRouter

from app.api.v1.endpoints import assessments, auth, chat, health, mood, users

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(auth.router, tags=["auth"])
router.include_router(users.router, tags=["users"])
router.include_router(assessments.router)
router.include_router(chat.router)
router.include_router(mood.router)
