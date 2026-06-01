import json
import logging
from collections.abc import AsyncGenerator

from anthropic import AsyncAnthropic
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.conversation import Conversation, Message
from app.schemas.chat import ExerciseCard, ExerciseStep
from app.services.mood import update_daily_mood

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

_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

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

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


def _pick_exercise_card(assistant_text: str) -> ExerciseCard | None:
    """Return an exercise card when the assistant response mentions a breathing exercise."""
    lower = assistant_text.lower()
    if any(kw in lower for kw in _EXERCISE_TRIGGER_KEYWORDS):
        return _BOX_BREATHING
    return None


async def _analyze_sentiment(content: str) -> str:
    """Classify user message sentiment via a lightweight Anthropic call.

    Uses a single-word response to minimize tokens and latency.
    Returns one of: "positive", "neutral", "negative".
    """
    response = await _anthropic.messages.create(
        model=_ANTHROPIC_MODEL,
        max_tokens=10,
        system=(
            "Classify the emotional sentiment of the Vietnamese text below. "
            "Reply with exactly one word: positive, neutral, or negative."
        ),
        messages=[{"role": "user", "content": content}],
    )
    raw = response.content[0].text.strip().lower()
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


async def list_conversations(db: AsyncSession, user_id: int) -> list[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
    )
    return list(result.scalars().all())


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
    """Save user message, stream Anthropic response, save assistant message.

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

    # Build message history for Anthropic (last N messages including the one just saved)
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(_MAX_HISTORY)
    )
    # Reverse so oldest-first (Anthropic requires chronological order)
    history = list(reversed(history_result.scalars().all()))
    anthropic_messages = [{"role": m.role, "content": m.content} for m in history]

    # Stream from Anthropic and buffer the full response
    full_response: list[str] = []
    try:
        async with _anthropic.messages.stream(
            model=_ANTHROPIC_MODEL,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=anthropic_messages,
        ) as stream:
            async for text in stream.text_stream:
                full_response.append(text)
                yield f"data: {json.dumps({'type': 'chunk', 'content': text})}\n\n"
    except Exception as e:
        logger.error("Anthropic stream error for conversation %d: %s", conversation_id, e)
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
    # The assistant message is already flushed above — committing here preserves both messages
    # even if the sentiment API call fails.
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
