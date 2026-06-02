import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.safety_plan import UserSafetyPlan
from app.schemas.safety_plan import SafetyPlanResponse, SafetyPlanUpsert, TrustedContact

logger = logging.getLogger(__name__)


def _contacts_to_db(contacts: list[TrustedContact]) -> list[str]:
    return [f"{c.name}|{c.phone}" for c in contacts]


def _contacts_from_db(raw: list[str]) -> list[TrustedContact]:
    result = []
    for entry in raw:
        if "|" in entry:
            name, phone = entry.split("|", 1)
            result.append(TrustedContact(name=name, phone=phone))
        else:
            logger.warning("Malformed trusted_contact entry skipped: %r", entry)
    return result


def _to_response(plan: UserSafetyPlan) -> SafetyPlanResponse:
    return SafetyPlanResponse(
        id=plan.id,
        warning_signs=plan.warning_signs,
        coping_activities=plan.coping_activities,
        trusted_contacts=_contacts_from_db(plan.trusted_contacts),
        reasons_to_live=plan.reasons_to_live,
        updated_at=plan.updated_at,
    )


async def get_safety_plan(db: AsyncSession, user_id: int) -> SafetyPlanResponse | None:
    result = await db.execute(
        select(UserSafetyPlan).where(UserSafetyPlan.user_id == user_id)
    )
    plan = result.scalar_one_or_none()
    return _to_response(plan) if plan else None


async def upsert_safety_plan(
    db: AsyncSession, user_id: int, payload: SafetyPlanUpsert
) -> SafetyPlanResponse:
    result = await db.execute(
        select(UserSafetyPlan).where(UserSafetyPlan.user_id == user_id)
    )
    plan = result.scalar_one_or_none()

    contacts_db = _contacts_to_db(payload.trusted_contacts)

    if plan is None:
        plan = UserSafetyPlan(
            user_id=user_id,
            warning_signs=payload.warning_signs,
            coping_activities=payload.coping_activities,
            trusted_contacts=contacts_db,
            reasons_to_live=payload.reasons_to_live,
        )
        db.add(plan)
    else:
        plan.warning_signs = payload.warning_signs
        plan.coping_activities = payload.coping_activities
        plan.trusted_contacts = contacts_db
        plan.reasons_to_live = payload.reasons_to_live

    await db.flush()
    await db.refresh(plan)
    return _to_response(plan)
