# Import all models so SQLAlchemy can resolve string-based relationship targets
# (e.g. "Assessment.created_at") regardless of import order elsewhere.
from . import (  # noqa: F401
    assessment,
    badge_notification,
    conversation,
    exercise,
    journal,
    mood,
    notification_preference,
    safety_plan,
    subscription,
    system_error,
    thought_record,
    user,
    wellness,
)
