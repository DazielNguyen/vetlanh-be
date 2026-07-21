"""Asynchronous, version-safe mood reflection generation.

Only deterministic statistics are allowed to contain numbers. The language model
receives those precomputed facts and cannot choose confidence, evidence, or URLs.
"""

import asyncio
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from groq import AsyncGroq
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.mood import MoodAnalysis, MoodAnalysisAudit, MoodEntry
from app.schemas.mood import (
    AgentMoodOutput,
    InsightsResponse,
    MoodNextAction,
    MoodReflection,
)
from app.services.crisis import CrisisLevel, detect_crisis_level
from app.services.exercise import get_exercise
from app.services.insights import get_insights
from app.services.mood import get_mood_factors

logger = logging.getLogger(__name__)

PROMPT_VERSION = "mood-reflection-v1"
_MODEL = "llama-3.3-70b-versatile"
_PROCESSING_TTL = timedelta(seconds=15)
_MODEL_TIMEOUT_SECONDS = 8
_RETRY_TIMEOUT_SECONDS = 6
_FORBIDDEN_CAUSAL_WORDS = ("chắc chắn", "gây ra", "chẩn đoán", "bạn bị", "bạn mắc")
_FORBIDDEN_CAUSAL_RE = re.compile(r"\bdo\b", re.IGNORECASE)
_MARKUP_RE = re.compile(r"<[^>]+>|(^|\s)[#*_`]|^\s*[-+>]\s", re.MULTILINE)
_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
_FACTOR_LABELS = {factor.key: factor.label for factor in get_mood_factors()}

# Keep strong references so fire-and-forget tasks are not garbage-collected.
_running_tasks: set[asyncio.Task] = set()


def _entry_version(entry: MoodEntry) -> datetime:
    value = entry.updated_at or entry.created_at
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def enqueue_analysis(db: AsyncSession, user_id: int, entry: MoodEntry) -> MoodAnalysis:
    """Create an idempotent processing job and make older jobs stale."""
    version = _entry_version(entry)
    existing_result = await db.execute(
        select(MoodAnalysis).where(
            MoodAnalysis.user_id == user_id,
            MoodAnalysis.entry_id == entry.id,
            MoodAnalysis.entry_updated_at == version,
            MoodAnalysis.prompt_version == PROMPT_VERSION,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return existing

    await db.execute(
        update(MoodAnalysis)
        .where(
            MoodAnalysis.user_id == user_id,
            MoodAnalysis.status == "processing",
        )
        .values(status="stale")
    )
    analysis = MoodAnalysis(
        user_id=user_id,
        entry_id=entry.id,
        entry_updated_at=version,
        prompt_version=PROMPT_VERSION,
        status="processing",
        generated_by="rules",
    )
    db.add(analysis)
    await db.flush()
    return analysis


def schedule_analysis(analysis_id: int) -> None:
    """Schedule work without extending the mood check-in response lifecycle."""
    task = asyncio.create_task(process_analysis(analysis_id))
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)


async def get_mood_statistics(
    db: AsyncSession, user_id: int, days: int = 30
) -> dict[str, Any]:
    """Return model-safe, deterministic aggregates scoped to exactly one user."""
    end = datetime.now(tz=timezone.utc).date()
    start = end - timedelta(days=days - 1)
    result = await db.execute(
        select(MoodEntry)
        .where(
            MoodEntry.user_id == user_id,
            MoodEntry.date >= start,
            MoodEntry.date <= end,
        )
        .order_by(MoodEntry.date.desc())
    )
    entries = list(result.scalars().all())

    windows: dict[str, dict[str, float | int | None]] = {}
    for window in (7, 14, 30):
        window_start = end - timedelta(days=window - 1)
        values = [e.mood for e in entries if e.date >= window_start]
        first_half = values[len(values) // 2 :]
        second_half = values[: len(values) // 2]
        trend = None
        if first_half and second_half:
            trend = round(
                sum(second_half) / len(second_half) - sum(first_half) / len(first_half),
                1,
            )
        windows[str(window)] = {
            "sample_size": len(values),
            "average": round(sum(values) / len(values), 1) if values else None,
            "trend": trend,
        }

    overall_average = sum(e.mood for e in entries) / len(entries) if entries else None
    factor_values: dict[str, list[int]] = defaultdict(list)
    for entry in entries:
        for factor in set(entry.factors):
            if factor in _FACTOR_LABELS:
                factor_values[factor].append(entry.mood)

    correlations = []
    if overall_average is not None:
        for factor, moods in factor_values.items():
            if len(moods) < 3:
                continue
            delta = round(sum(moods) / len(moods) - overall_average, 1)
            if abs(delta) < 0.3:
                continue
            correlations.append(
                {
                    "factor": factor,
                    "sample_size": len(moods),
                    "total_entries": len(entries),
                    "delta": delta,
                }
            )
    correlations.sort(key=lambda item: (-abs(item["delta"]), item["factor"]))

    return {
        "windows": windows,
        "factor_correlations": correlations,
        "missing_data": len(entries) < days,
    }


def _confidence_and_evidence(statistics: dict[str, Any]) -> tuple[str, str | None]:
    correlations = statistics["factor_correlations"]
    if not correlations:
        return "low", None
    strongest = correlations[0]
    n = strongest["sample_size"]
    strength = abs(strongest["delta"])
    if n >= 7 and strength >= 0.8:
        confidence = "high"
    elif n >= 4 and strength >= 0.5:
        confidence = "medium"
    else:
        return "low", None
    label = _FACTOR_LABELS[strongest["factor"]]
    return confidence, f"{n} trong {strongest['total_entries']} lần có yếu tố {label}"


def _safe_action(entry: MoodEntry, crisis_level: CrisisLevel) -> MoodNextAction | None:
    if crisis_level >= CrisisLevel.LEVEL_2_SERIOUS:
        return MoodNextAction(
            type="chat",
            title="Kết nối hỗ trợ ngay",
            description="Bạn không cần ở một mình với cảm giác này.",
            url="/services/chat",
        )
    if entry.mood > 3 and entry.energy != "low":
        return None
    slug = "coherent-breathing" if entry.energy == "low" else "box-breathing"
    exercise = get_exercise(slug)
    if exercise is None or exercise.duration_minutes > 5:
        return None
    return MoodNextAction(
        type="exercise",
        title=exercise.title,
        description=exercise.description[:120],
        url=f"/services/exercises/{exercise.slug}",
    )


def _validate_agent_text(output: AgentMoodOutput) -> None:
    values = [output.acknowledgement, output.observation, output.follow_up_prompt or ""]
    combined = " ".join(values).lower()
    if any(word in combined for word in _FORBIDDEN_CAUSAL_WORDS) or _FORBIDDEN_CAUSAL_RE.search(
        combined
    ):
        raise ValueError("Unsafe diagnostic or causal language in model output")
    if any(_MARKUP_RE.search(value) for value in values):
        raise ValueError("Markup is not allowed in model output")
    # All displayed quantitative evidence is appended from deterministic statistics.
    # Rejecting digits here prevents the model from inventing a count or correlation.
    if any(re.search(r"\d", value) for value in values):
        raise ValueError("Model-authored numbers are not allowed")


async def _generate_agent_output(
    entry: MoodEntry, statistics: dict[str, Any]
) -> AgentMoodOutput:
    safe_context = {
        "today": {
            "mood": entry.mood,
            "energy": entry.energy,
            "factors": [factor for factor in entry.factors if factor in _FACTOR_LABELS],
            "note": entry.note,
        },
        "statistics": statistics,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "Bạn viết phản hồi mood bằng tiếng Việt, bình tĩnh, cụ thể, không phán xét. "
                "Không chẩn đoán, không khuyên thuốc, không khẳng định nhân quả, không Markdown/HTML. "
                "Không tự tính, thêm hoặc viết bất kỳ chữ số nào; backend sẽ gắn evidence riêng. "
                "Trả đúng JSON gồm acknowledgement, observation, action_title, "
                "action_description, follow_up_prompt. acknowledgement tối đa 140 ký tự; "
                "observation tối đa 260 ký tự. Mỗi trường chỉ 1-2 câu ngắn."
            ),
        },
        {"role": "user", "content": json.dumps(safe_context, ensure_ascii=False)},
    ]
    response = await _client.chat.completions.create(
        model=_MODEL,
        messages=messages,
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Model returned an empty response")
    output = AgentMoodOutput.model_validate_json(content)
    _validate_agent_text(output)
    return output


async def _generate_with_retry(entry: MoodEntry, statistics: dict[str, Any]) -> AgentMoodOutput:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            timeout = _MODEL_TIMEOUT_SECONDS if attempt == 0 else _RETRY_TIMEOUT_SECONDS
            return await asyncio.wait_for(
                _generate_agent_output(entry, statistics),
                timeout=timeout,
            )
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                await asyncio.sleep(0.25)
    assert last_error is not None
    raise last_error


async def _is_current_job(db: AsyncSession, analysis: MoodAnalysis, entry: MoodEntry) -> bool:
    latest_result = await db.execute(
        select(MoodAnalysis.id)
        .where(MoodAnalysis.user_id == analysis.user_id)
        .order_by(MoodAnalysis.created_at.desc(), MoodAnalysis.id.desc())
        .limit(1)
    )
    latest_id = latest_result.scalar_one_or_none()
    version_result = await db.execute(
        select(MoodEntry.updated_at).where(
            MoodEntry.id == entry.id,
            MoodEntry.user_id == analysis.user_id,
        )
    )
    current_version = version_result.scalar_one_or_none()
    if current_version is not None and current_version.tzinfo is None:
        current_version = current_version.replace(tzinfo=timezone.utc)
    return latest_id == analysis.id and current_version == analysis.entry_updated_at


async def process_analysis(analysis_id: int) -> None:
    """Worker entrypoint. It never publishes unless this is still the newest version."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MoodAnalysis, MoodEntry)
                .join(MoodEntry, MoodEntry.id == MoodAnalysis.entry_id)
                .where(MoodAnalysis.id == analysis_id)
            )
            row = result.one_or_none()
            if row is None:
                return
            analysis, entry = row
            if analysis.status != "processing" or not await _is_current_job(db, analysis, entry):
                analysis.status = "stale"
                await db.commit()
                return

            statistics = await get_mood_statistics(db, analysis.user_id)
            crisis_level = detect_crisis_level(entry.note or "")
            action = _safe_action(entry, crisis_level)

            if crisis_level >= CrisisLevel.LEVEL_2_SERIOUS:
                db.add(
                    MoodAnalysisAudit(
                        user_id=analysis.user_id,
                        entry_id=entry.id,
                        event_type="mood_note_crisis_signal",
                    )
                )
                output = AgentMoodOutput(
                    acknowledgement="Mình nghe thấy rằng lúc này đang rất nặng nề với bạn.",
                    observation="Ưu tiên lúc này là kết nối với một người hoặc kênh hỗ trợ an toàn.",
                    follow_up_prompt="Tôi cần được hỗ trợ ngay lúc này.",
                )
                generated_by = "rules"
            else:
                try:
                    output = await _generate_with_retry(entry, statistics)
                    generated_by = "agent"
                except Exception as exc:
                    # Never log the prompt or note; exception type is enough for operations.
                    logger.warning("Mood reflection generation failed: %s", type(exc).__name__)
                    if await _is_current_job(db, analysis, entry):
                        analysis.status = "unavailable"
                        analysis.generated_by = "rules"
                        analysis.generated_at = datetime.now(tz=timezone.utc)
                        await db.commit()
                    return

            if not await _is_current_job(db, analysis, entry):
                analysis.status = "stale"
                await db.commit()
                return

            confidence, evidence = _confidence_and_evidence(statistics)
            analysis.reflection = MoodReflection(
                acknowledgement=output.acknowledgement,
                observation=output.observation,
                evidence=evidence,
                confidence=confidence,
            ).model_dump(mode="json")
            analysis.next_action = action.model_dump(mode="json") if action else None
            analysis.follow_up_prompt = output.follow_up_prompt
            analysis.status = "ready"
            analysis.generated_by = generated_by
            analysis.generated_at = datetime.now(tz=timezone.utc)
            await db.commit()
    except Exception:
        # A worker failure must never affect the already committed check-in.
        logger.exception("Unexpected mood analysis worker failure for analysis_id=%s", analysis_id)


async def recover_pending_analyses() -> None:
    """Resume recent persisted jobs and reap jobs left hanging across a restart."""
    now = datetime.now(tz=timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MoodAnalysis).where(MoodAnalysis.status == "processing")
        )
        for analysis in result.scalars().all():
            created_at = analysis.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if now - created_at > _PROCESSING_TTL:
                analysis.status = "unavailable"
                analysis.generated_by = "rules"
                analysis.generated_at = now
            else:
                schedule_analysis(analysis.id)
        await db.commit()


async def shutdown_analysis_tasks() -> None:
    """Cancel in-process workers cleanly; persisted jobs are recovered next startup."""
    tasks = list(_running_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def get_agentic_insights(db: AsyncSession, user_id: int) -> InsightsResponse:
    """Combine latest job state with backward-compatible deterministic insights."""
    rules = await get_insights(db, user_id)
    result = await db.execute(
        select(MoodAnalysis, MoodEntry.updated_at)
        .join(MoodEntry, MoodEntry.id == MoodAnalysis.entry_id)
        .where(MoodAnalysis.user_id == user_id, MoodAnalysis.status != "stale")
        .order_by(MoodAnalysis.created_at.desc(), MoodAnalysis.id.desc())
        .limit(1)
    )
    row = result.one_or_none()
    if row is None:
        return rules
    analysis, current_entry_version = row

    if current_entry_version.tzinfo is None:
        current_entry_version = current_entry_version.replace(tzinfo=timezone.utc)
    if current_entry_version != analysis.entry_updated_at:
        # The check-in was saved but its enqueue failed. Never expose the previous
        # version as current; degrade to rules until another job is enqueued.
        analysis.status = "unavailable"
        analysis.generated_by = "rules"
        analysis.generated_at = datetime.now(tz=timezone.utc)
        analysis.reflection = None
        analysis.next_action = None
        analysis.follow_up_prompt = None
        await db.flush()

    now = datetime.now(tz=timezone.utc)
    created_at = analysis.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if analysis.status == "processing" and now - created_at > _PROCESSING_TTL:
        analysis.status = "unavailable"
        analysis.generated_by = "rules"
        analysis.generated_at = now
        await db.flush()

    exposed_status = analysis.status
    if exposed_status not in {"processing", "ready", "unavailable"}:
        exposed_status = "unavailable"
    return InsightsResponse(
        status=exposed_status,
        analysis_for_entry_id=str(analysis.entry_id),
        total_entries=rules.total_entries,
        has_enough_data=rules.has_enough_data,
        generated_by=analysis.generated_by,
        generated_at=analysis.generated_at,
        reflection=analysis.reflection if exposed_status == "ready" else None,
        next_action=analysis.next_action if exposed_status == "ready" else None,
        follow_up_prompt=analysis.follow_up_prompt if exposed_status == "ready" else None,
        insights=rules.insights,
    )
