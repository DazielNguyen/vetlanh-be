from fastapi import APIRouter

from app.api.v1.endpoints import assessments, auth, chat, crisis, dashboard, exercises, health, journal, mood, safety_plan, thought_records, users

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(auth.router, tags=["auth"])
router.include_router(users.router, tags=["users"])
router.include_router(assessments.router)
router.include_router(chat.router)
router.include_router(mood.router)
router.include_router(journal.router)
router.include_router(exercises.router)
router.include_router(crisis.router)
router.include_router(safety_plan.router)
router.include_router(thought_records.router)
router.include_router(dashboard.router)
