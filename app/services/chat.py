import json
import logging
from collections.abc import AsyncGenerator

import aioboto3
from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.conversation import Conversation, Message
from app.schemas.chat import ConversationListItem, ExerciseCard, ExerciseStep
from app.services.mood import update_daily_mood

_session = aioboto3.Session(
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_REGION,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Bạn là Vet, một người bạn đồng hành thấu cảm và ấm áp của ứng dụng VetLanh.
Nhiệm vụ của bạn là lắng nghe người dùng không phán xét, giúp họ cảm thấy được thấu hiểu và nhẹ lòng hơn.

Quy tắc quan trọng:
- Luôn dùng tiếng Việt
- Không đưa ra lời khuyên y tế hoặc chẩn đoán bệnh
- Không khuyên người dùng uống thuốc
- Nếu người dùng có biểu hiện khủng hoảng, gợi ý họ gọi đường dây hỗ trợ 1800 599 920
- Giữ phản hồi ngắn gọn (2–4 câu), tự nhiên như người bạn
- Đặt câu hỏi mở để khuyến khích người dùng chia sẻ thêm

Kỹ thuật CBT (Cognitive Behavioral Therapy):
- Khi người dùng dùng ngôn ngữ cực đoan như "không bao giờ", "luôn luôn", "tôi thật vô dụng",
  "chẳng ai quan tâm", "tôi chẳng làm được gì" — nhẹ nhàng nhận ra cảm xúc đó trước
- Sau đó hỏi họ: "Bạn có muốn thử nhìn tình huống này theo một cách khác không?" trước khi gợi ý
- Dùng câu hỏi Socratic: "Điều gì khiến bạn nghĩ vậy?", "Có lúc nào khác bạn cảm thấy khác không?"
- Không áp đặt — luôn hỏi trước khi dẫn dắt reframe

Gợi ý bài tập thở:
- Khi người dùng thể hiện lo âu, căng thẳng, tim đập nhanh, khó thở — gợi ý bài tập thở
- Dùng câu: "Mình có một bài tập thở ngắn có thể giúp bạn bình tĩnh lại ngay bây giờ, bạn có muốn thử không?"
- Sau khi gợi ý xong, tiếp tục hội thoại bình thường"""

# Limit context window to last 20 messages to control token usage
_MAX_HISTORY = 20

# Consecutive negative user messages before suggesting a check-in
_NEGATIVE_STREAK_THRESHOLD = 5

# Keywords in assistant response that indicate a breathing exercise was suggested
_EXERCISE_TRIGGER_KEYWORDS = [
    "bài tập thở",
    "hít thở",
    "thở hộp",
    "thở 4",
    "hít vào",
    "thở ra",
]

# Llama 3.2 11B — no Anthropic approval needed; switch to Claude when AWS unlocks it
# To switch back to Claude: "us.anthropic.claude-3-5-haiku-20241022-v1:0"
_BEDROCK_MODEL = "us.meta.llama3-2-11b-instruct-v1:0"

_BOX_BREATHING = ExerciseCard(
    id="box-breathing",
    title="Thở Hộp (Box Breathing)",
    description="Kỹ thuật thở 4-4-4-4 giúp hệ thần kinh bình tĩnh lại trong 2 phút.",
    steps=[
        ExerciseStep(order=1, instruction="Hít vào từ từ qua mũi", duration_seconds=4),
        ExerciseStep(order=2, instruction="Giữ hơi thở", duration_seconds=4),
        ExerciseStep(order=3, instruction="Thở ra từ từ qua miệng", duration_seconds=4),
        ExerciseStep(order=4, instruction="Giữ trống phổi", duration_seconds=4),
        ExerciseStep(order=5, instruction="Lặp lại 4 lần", duration_seconds=None),
    ],
)


def _build_converse_messages(history: list[Message]) -> list[dict]:
    """Convert DB messages to Bedrock Converse API format."""
    return [
        {"role": m.role, "content": [{"text": m.content}]}
        for m in history
    ]


def _pick_exercise_card(assistant_text: str) -> ExerciseCard | None:
    """Return an exercise card when the assistant response mentions a breathing exercise."""
    lower = assistant_text.lower()
    if any(kw in lower for kw in _EXERCISE_TRIGGER_KEYWORDS):
        return _BOX_BREATHING
    return None


async def _analyze_sentiment(content: str) -> str:
    """Classify user message sentiment via a lightweight Bedrock Converse call.

    Uses a single-word response to minimize tokens and latency.
    Returns one of: "positive", "neutral", "negative".
    """
    prompt = (
        "Classify the emotional sentiment of the Vietnamese text below. "
        "Reply with exactly one word: positive, neutral, or negative.\n\n"
        f"{content}"
    )
    async with _session.client("bedrock-runtime") as client:
        response = await client.converse(
            modelId=_BEDROCK_MODEL,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 10},
        )
    raw = response["output"]["message"]["content"][0]["text"].strip().lower()
    if raw in ("positive", "neutral", "negative"):
        return raw
    return "neutral"


async def _check_negative_streak(db: AsyncSession, conversation_id: int) -> bool:
    """Return True when the last N consecutive user messages are all negative."""
    result = await db.execute(
        select(Message.sentiment)
        .where(
            Message.conversation_id == conversation_id,
            Message.role == "user",
            Message.sentiment.isnot(None),
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(_NEGATIVE_STREAK_THRESHOLD)
    )
    recent_sentiments = [row[0] for row in result.all()]
    return (
        len(recent_sentiments) >= _NEGATIVE_STREAK_THRESHOLD
        and all(s == "negative" for s in recent_sentiments)
    )


async def create_conversation(db: AsyncSession, user_id: int, title: str | None = None) -> Conversation:
    conv = Conversation(user_id=user_id, title=title)
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return conv


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_conversations(
    db: AsyncSession, user_id: int, q: str | None = None
) -> list[ConversationListItem]:
    msg_count = (
        select(func.count(Message.id))
        .where(Message.conversation_id == Conversation.id)
        .correlate(Conversation)
        .scalar_subquery()
    )
    last_msg_at = (
        select(func.max(Message.created_at))
        .where(Message.conversation_id == Conversation.id)
        .correlate(Conversation)
        .scalar_subquery()
    )
    last_msg_preview = (
        select(func.substr(Message.content, 1, 100))
        .where(Message.conversation_id == Conversation.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
    )
    query = (
        select(
            Conversation.id,
            Conversation.title,
            Conversation.created_at,
            Conversation.updated_at,
            msg_count.label("message_count"),
            last_msg_at.label("last_message_at"),
            last_msg_preview.label("last_message_preview"),
        )
        .where(Conversation.user_id == user_id)
        .order_by(func.coalesce(last_msg_at, Conversation.created_at).desc())
    )
    if q:
        pattern = f"%{_escape_like(q)}%"
        msg_match = (
            select(Message.id)
            .where(
                Message.conversation_id == Conversation.id,
                Message.content.ilike(pattern, escape="\\"),
            )
            .correlate(Conversation)
            .exists()
        )
        query = query.where(
            or_(
                Conversation.title.ilike(pattern, escape="\\"),
                msg_match,
            )
        )
    result = await db.execute(query)
    return [ConversationListItem(**row._mapping) for row in result.all()]


async def _get_conversation(db: AsyncSession, conversation_id: int, user_id: int) -> Conversation | None:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def delete_conversation(db: AsyncSession, conversation_id: int, user_id: int) -> bool:
    conv = await _get_conversation(db, conversation_id, user_id)
    if conv is None:
        return False
    await db.delete(conv)
    await db.flush()
    return True


async def get_conversation_or_403(db: AsyncSession, conversation_id: int, user_id: int) -> Conversation:
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return conv


async def get_messages(db: AsyncSession, conversation_id: int, user_id: int) -> list[Message]:
    await get_conversation_or_403(db, conversation_id, user_id)
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars().all())


async def stream_chat(
    db: AsyncSession,
    conversation_id: int,
    user_id: int,
    user_content: str,
) -> AsyncGenerator[str, None]:
    """Save user message, stream Bedrock response, save assistant message.

    Yields SSE-formatted strings. The final 'done' event includes:
      message_id      — persisted assistant message ID
      exercise_card   — breathing exercise card if AI suggested one, else null
      sentiment       — user message sentiment: positive | neutral | negative
      suggest_checkin — true when user sent 5+ consecutive negative messages
    """
    conv = await get_conversation_or_403(db, conversation_id, user_id)

    # Persist user message immediately so history is consistent on reconnect
    user_msg = Message(conversation_id=conversation_id, role="user", content=user_content)
    db.add(user_msg)
    await db.flush()
    await db.refresh(user_msg)

    # Build message history for Bedrock (last N messages including the one just saved)
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(_MAX_HISTORY)
    )
    # Reverse so oldest-first (Bedrock requires chronological order)
    history = list(reversed(history_result.scalars().all()))
    converse_messages = _build_converse_messages(history)

    # Stream from Bedrock and buffer the full response
    full_response: list[str] = []
    try:
        async with _session.client("bedrock-runtime") as client:
            response = await client.converse_stream(
                modelId=_BEDROCK_MODEL,
                system=[{"text": _SYSTEM_PROMPT}],
                messages=converse_messages,
                inferenceConfig={"maxTokens": 1024},
            )
            async for event in response["stream"]:
                if "contentBlockDelta" in event:
                    text = event["contentBlockDelta"]["delta"].get("text", "")
                    if text:
                        full_response.append(text)
                        yield f"data: {json.dumps({'type': 'chunk', 'content': text})}\n\n"
    except Exception as e:
        logger.error("Bedrock stream error for conversation %d: %s", conversation_id, e)
        # Rollback the flushed user_msg so there is no orphaned message with no paired reply
        await db.rollback()
        yield f"data: {json.dumps({'type': 'error', 'detail': 'Không thể kết nối với AI. Vui lòng thử lại.'})}\n\n"
        return

    # Save assistant message after stream completes
    assistant_content = "".join(full_response)
    assistant_msg = Message(
        conversation_id=conversation_id, role="assistant", content=assistant_content
    )
    db.add(assistant_msg)
    await db.flush()
    await db.refresh(assistant_msg)

    # Analyze sentiment post-stream; degrade gracefully on failure so messages are never lost.
    sentiment: str | None = None
    suggest_checkin = False
    try:
        sentiment = await _analyze_sentiment(user_content)
        user_msg.sentiment = sentiment
        # Flush so _check_negative_streak sees the current message's sentiment in its query
        await db.flush()
        suggest_checkin = await _check_negative_streak(db, conversation_id)
        await update_daily_mood(db, conv.user_id, sentiment)
    except Exception as e:
        logger.error("Sentiment analysis failed for message %d: %s", user_msg.id, e)

    exercise_card = _pick_exercise_card(assistant_content)

    await db.commit()

    done_payload: dict = {
        "type": "done",
        "message_id": assistant_msg.id,
        "exercise_card": exercise_card.model_dump() if exercise_card else None,
        "sentiment": sentiment,
        "suggest_checkin": suggest_checkin,
    }
    yield f"data: {json.dumps(done_payload)}\n\n"
