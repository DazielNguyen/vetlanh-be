from fastapi import APIRouter

from app.api.v1.endpoints import (
    articles,
    assessments,
    auth,
    badges,
    chat,
    community,
    crisis,
    dashboard,
    errors,
    exercises,
    feedback,
    health,
    journal,
    journal_prompts,
    mood,
    notifications,
    reflections,
    resources,
    safety_plan,
    sounds,
    subscriptions,
    thought_records,
    users,
    wellness,
)
from app.api.v1.endpoints.admin import router as admin_router

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(auth.router, tags=["auth"])
router.include_router(users.router, tags=["users"])
router.include_router(assessments.router)
router.include_router(chat.router)
router.include_router(mood.router)
# journal_prompts MUST be registered before journal to avoid /{entry_id} wildcard matching first
router.include_router(journal_prompts.router)
router.include_router(journal.router)
router.include_router(exercises.router)
router.include_router(crisis.router)
router.include_router(safety_plan.router)
router.include_router(thought_records.router)
router.include_router(reflections.router)
router.include_router(dashboard.router)
router.include_router(badges.router)
router.include_router(notifications.router)
router.include_router(resources.router)
router.include_router(sounds.router)
router.include_router(articles.router)
router.include_router(community.router)
router.include_router(wellness.router)
router.include_router(subscriptions.router)
router.include_router(errors.router)
router.include_router(feedback.router)
router.include_router(admin_router)
