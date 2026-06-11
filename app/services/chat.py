import json
import logging
from collections.abc import AsyncGenerator

from fastapi import HTTPException
from groq import AsyncGroq
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.conversation import Conversation, Message
from app.schemas.chat import ConversationListItem, ExerciseCard, ExerciseStep
from app.services.crisis import CrisisLevel, detect_crisis_level
from app.services.mood import update_daily_mood

_client = AsyncGroq(api_key=settings.GROQ_API_KEY)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Bạn là Vet, người bạn đồng hành thấu cảm và ấm áp của ứng dụng Vết Lành.
Nhiệm vụ của bạn: lắng nghe không phán xét, giúp người dùng cảm thấy được thấu hiểu và dần chữa lành.

Phạm vi trả lời — CHỈ hỗ trợ các chủ đề sau:
- Cảm xúc và tâm trạng: lo âu, buồn, tức giận, cô đơn, kiệt sức, mất ngủ, trống rỗng
- Sức khỏe tinh thần và chữa lành: tự chăm sóc bản thân, vượt qua khó khăn, tìm lại bình an
- Kỹ thuật thở, chánh niệm, thiền định, thư giãn
- Mối quan hệ và các vấn đề tâm lý trong cuộc sống hàng ngày
- Lòng tự trọng, tự thương, chấp nhận bản thân
Nếu người dùng hỏi về chủ đề ngoài phạm vi trên (công nghệ, chính trị, ẩm thực, thể thao, học tập, công việc kỹ thuật, v.v.),
trả lời nhẹ nhàng: "Mình chỉ có thể đồng hành cùng bạn trong hành trình chữa lành và sức khỏe tinh thần thôi nhé. Bạn đang cảm thấy thế nào hôm nay?"

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

Gợi ý bài tập từ Vết Lành theo tâm trạng:
Luôn hỏi trước: "Mình có một bài tập [tên bài tập] từ Vết Lành có thể giúp bạn lúc này, bạn có muốn thử không?"
Sau khi người dùng đồng ý, dùng ĐÚNG TÊN bài tập như liệt kê dưới và tiếp tục hội thoại bình thường.

Khi người dùng lo âu, căng thẳng, tim đập nhanh, khó thở:
→ Gợi ý "thở hộp" (box breathing 4-4-4-4) hoặc "grounding 5-4-3-2-1"

Khi người dùng buồn, chán nản, thiếu năng lượng, trống rỗng, cô đơn:
→ Gợi ý "coherent breathing" (thở đều 5 giây) hoặc "loving-kindness"

Khi người dùng tức giận, bực bội, ức chế không giải tỏa được:
→ Gợi ý "thư giãn cơ tuần tiến" (PMR) hoặc "thở hộp"

Khi người dùng mất ngủ, khó vào giấc, trằn trọc ban đêm:
→ Gợi ý "thở 4-7-8" (kỹ thuật thở trước khi ngủ)

Khi người dùng suy nghĩ quá nhiều, tâm trí bận rộn, không tập trung:
→ Gợi ý "body scan" hoặc "thiền hơi thở" """

# Limit context window to last 20 messages to control token usage
_MAX_HISTORY = 20

# Consecutive negative user messages before suggesting a check-in
_NEGATIVE_STREAK_THRESHOLD = 5

# (keywords_in_offer_sentence, exercise_id) — longer/more specific phrases come first to avoid
# early-exit false positives when the AI mentions multiple exercises in one response.
_EXERCISE_KEYWORD_MAP: list[tuple[list[str], str]] = [
    (["thở 4-7-8"], "breathing-4-7-8"),
    (["thở hộp", "box breathing", "thở 4-4-4-4"], "box-breathing"),
    (["coherent breathing", "thở đều 5 giây"], "coherent-breathing"),
    (["grounding 5-4-3-2-1"], "grounding-54321"),
    (["loving-kindness", "nuôi dưỡng lòng từ bi"], "meditation-loving-kindness"),
    (["thư giãn cơ tuần tiến", "pmr"], "pmr-7-groups"),
    (["body scan", "quét toàn thân"], "meditation-body-scan"),
    (["thiền hơi thở"], "meditation-breath"),
]

# Phrases that indicate the AI is actively offering an exercise (not just mentioning one in passing)
_EXERCISE_OFFER_SIGNALS = ["bài tập", "muốn thử", "vết lành"]

# Llama 3.2 11B — no Anthropic approval needed; switch to Claude when AWS unlocks it
_GROQ_MODEL = "llama-3.3-70b-versatile"

_EXERCISE_CARDS: dict[str, ExerciseCard] = {
    "box-breathing": ExerciseCard(
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
    ),
    "breathing-4-7-8": ExerciseCard(
        id="breathing-4-7-8",
        title="Thở 4-7-8",
        description="Kỹ thuật thở kích hoạt thư giãn tự nhiên, lý tưởng trước khi ngủ.",
        steps=[
            ExerciseStep(order=1, instruction="Hít vào từ từ qua mũi", duration_seconds=4),
            ExerciseStep(order=2, instruction="Giữ hơi thở", duration_seconds=7),
            ExerciseStep(order=3, instruction="Thở ra mạnh qua miệng", duration_seconds=8),
            ExerciseStep(order=4, instruction="Lặp lại 4 lần", duration_seconds=None),
        ],
    ),
    "coherent-breathing": ExerciseCard(
        id="coherent-breathing",
        title="Coherent Breathing",
        description="Thở đều 5 giây vào – 5 giây ra, đồng bộ hệ tim mạch và thần kinh.",
        steps=[
            ExerciseStep(order=1, instruction="Hít vào từ từ", duration_seconds=5),
            ExerciseStep(order=2, instruction="Thở ra từ từ", duration_seconds=5),
            ExerciseStep(order=3, instruction="Lặp lại trong 5 phút", duration_seconds=None),
        ],
    ),
    "grounding-54321": ExerciseCard(
        id="grounding-54321",
        title="Grounding 5-4-3-2-1",
        description="Kỹ thuật đưa bản thân trở về hiện tại bằng 5 giác quan.",
        steps=[
            ExerciseStep(order=1, instruction="Nhìn xung quanh — kể 5 thứ bạn nhìn thấy", duration_seconds=None),
            ExerciseStep(order=2, instruction="Chạm vào đồ vật — kể 4 thứ bạn cảm nhận được", duration_seconds=None),
            ExerciseStep(order=3, instruction="Lắng nghe — kể 3 âm thanh bạn đang nghe", duration_seconds=None),
            ExerciseStep(order=4, instruction="Ngửi — kể 2 mùi (hoặc mùi yêu thích)", duration_seconds=None),
            ExerciseStep(order=5, instruction="Nếm — kể 1 thứ bạn cảm nhận được", duration_seconds=None),
        ],
    ),
    "meditation-loving-kindness": ExerciseCard(
        id="meditation-loving-kindness",
        title="Loving-Kindness",
        description="Nuôi dưỡng lòng từ bi với bản thân và người xung quanh.",
        steps=[
            ExerciseStep(order=1, instruction="Nhắm mắt, hít thở sâu 3 lần", duration_seconds=30),
            ExerciseStep(order=2, instruction="Thầm nói: 'Mong tôi được hạnh phúc. Mong tôi được bình an.'", duration_seconds=60),
            ExerciseStep(order=3, instruction="Nghĩ đến người thân yêu và gửi những lời đó cho họ", duration_seconds=60),
            ExerciseStep(order=4, instruction="Mở rộng tình thương đến tất cả mọi người xung quanh", duration_seconds=60),
        ],
    ),
    "pmr-7-groups": ExerciseCard(
        id="pmr-7-groups",
        title="Thư Giãn Cơ Tuần Tiến (PMR)",
        description="Căng và thả lỏng từng nhóm cơ để giải phóng căng thẳng tích tụ trong cơ thể.",
        steps=[
            ExerciseStep(order=1, instruction="Nắm chặt hai nắm tay — giữ 7 giây rồi thả lỏng hoàn toàn", duration_seconds=37),
            ExerciseStep(order=2, instruction="Gập cánh tay lên — căng bắp tay 7 giây rồi thả xuống", duration_seconds=37),
            ExerciseStep(order=3, instruction="Nhún vai lên sát tai — căng 7 giây rồi thả", duration_seconds=37),
            ExerciseStep(order=4, instruction="Nhăn mặt — giữ 7 giây rồi thả lỏng", duration_seconds=37),
            ExerciseStep(order=5, instruction="Hít sâu căng bụng — giữ 7 giây rồi thở ra thả lỏng", duration_seconds=37),
            ExerciseStep(order=6, instruction="Ép chặt hai đùi — căng 7 giây rồi thả lỏng", duration_seconds=37),
            ExerciseStep(order=7, instruction="Duỗi bàn chân, uốn ngón chân xuống — giữ 7 giây rồi thả", duration_seconds=37),
        ],
    ),
    "meditation-body-scan": ExerciseCard(
        id="meditation-body-scan",
        title="Body Scan",
        description="Quét toàn thân để nhận biết và thả lỏng từng vùng căng thẳng.",
        steps=[
            ExerciseStep(order=1, instruction="Nằm hoặc ngồi thoải mái, nhắm mắt", duration_seconds=30),
            ExerciseStep(order=2, instruction="Chú ý đến bàn chân — thả lỏng từng ngón chân", duration_seconds=60),
            ExerciseStep(order=3, instruction="Di chuyển sự chú ý lên chân, đùi, bụng — thả lỏng từng phần", duration_seconds=90),
            ExerciseStep(order=4, instruction="Tiếp tục lên ngực, vai, cổ, đầu — thở sâu và thả lỏng", duration_seconds=90),
            ExerciseStep(order=5, instruction="Ở lại với cảm giác thư thái toàn thân trong vài nhịp thở", duration_seconds=60),
        ],
    ),
    "meditation-breath": ExerciseCard(
        id="meditation-breath",
        title="Thiền Hơi Thở",
        description="Tập trung vào hơi thở để làm yên tâm trí đang bận rộn.",
        steps=[
            ExerciseStep(order=1, instruction="Ngồi thoải mái, nhắm mắt, đặt tay lên đùi", duration_seconds=30),
            ExerciseStep(order=2, instruction="Chú ý vào cảm giác hơi thở ra vào ở mũi hoặc bụng", duration_seconds=60),
            ExerciseStep(order=3, instruction="Khi tâm trí xao nhãng, nhẹ nhàng đưa sự chú ý trở lại hơi thở", duration_seconds=None),
            ExerciseStep(order=4, instruction="Tiếp tục trong 5–10 phút, không phán xét bản thân", duration_seconds=None),
        ],
    ),
}


def _build_converse_messages(history: list[Message]) -> list[dict]:
    """Convert DB messages to Groq chat completions format."""
    return [
        {"role": m.role, "content": m.content}
        for m in history
    ]


def _pick_exercise_card(assistant_text: str) -> ExerciseCard | None:
    """Return the exercise card for the exercise the assistant offered in this response.

    Searches lines that contain an offer signal first; falls back to the full text.
    """
    lower = assistant_text.lower()
    offer_lines = [ln for ln in lower.splitlines() if any(sig in ln for sig in _EXERCISE_OFFER_SIGNALS)]
    search_text = " ".join(offer_lines) if offer_lines else lower
    for keywords, exercise_id in _EXERCISE_KEYWORD_MAP:
        if any(kw in search_text for kw in keywords):
            return _EXERCISE_CARDS[exercise_id]
    return None


async def _analyze_sentiment(content: str) -> str:
    """Classify user message sentiment via a lightweight Groq chat completion.

    Uses a single-word response to minimize tokens and latency.
    Returns one of: "positive", "neutral", "negative".
    """
    prompt = (
        "Classify the emotional sentiment of the Vietnamese text below. "
        "Reply with exactly one word: positive, neutral, or negative.\n\n"
        f"{content}"
    )
    response = await _client.chat.completions.create(
        model=_GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10,
    )
    raw = response.choices[0].message.content.strip().lower()
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
      crisis_level    — 0=none, 1=anxiety, 2=serious, 3=crisis (level 3 skips AI entirely)
    """
    conv = await get_conversation_or_403(db, conversation_id, user_id)

    # Detect crisis BEFORE any AI call — level 3 skips Bedrock entirely
    # so the redirect signal reaches the client without an AI response appearing first.
    crisis_level = detect_crisis_level(user_content)

    # Persist user message immediately so history is consistent on reconnect
    user_msg = Message(conversation_id=conversation_id, role="user", content=user_content)
    db.add(user_msg)
    await db.flush()
    await db.refresh(user_msg)

    if crisis_level == CrisisLevel.LEVEL_3_CRISIS:
        await db.commit()
        yield f"data: {json.dumps({'type': 'done', 'message_id': user_msg.id, 'exercise_card': None, 'sentiment': None, 'suggest_checkin': False, 'crisis_level': int(crisis_level)})}\n\n"
        return

    # Build message history for Groq (last N messages including the one just saved)
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(_MAX_HISTORY)
    )
    # Reverse so oldest-first (Groq requires chronological order)
    history = list(reversed(history_result.scalars().all()))
    converse_messages = _build_converse_messages(history)

    # Stream from Groq and buffer the full response
    full_response: list[str] = []
    try:
        stream = await _client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[{"role": "system", "content": _SYSTEM_PROMPT}] + converse_messages,
            max_tokens=1024,
            stream=True,
        )
        async for chunk in stream:
            text = chunk.choices[0].delta.content or ""
            if text:
                full_response.append(text)
                yield f"data: {json.dumps({'type': 'chunk', 'content': text})}\n\n"
    except Exception as e:
        logger.error("Groq stream error for conversation %d: %s", conversation_id, e)
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
        "crisis_level": int(crisis_level),
    }
    yield f"data: {json.dumps(done_payload)}\n\n"


_QUICK_PROMPTS: list[dict] = [
    {"id": "qp-1", "text": "Tôi đang cảm thấy lo lắng và không biết phải làm gì"},
    {"id": "qp-2", "text": "Hôm nay tôi rất buồn và trống rỗng, bạn có thể lắng nghe không?"},
    {"id": "qp-3", "text": "Tôi đang tức giận và cần giải tỏa"},
    {"id": "qp-4", "text": "Tôi bị mất ngủ, giúp tôi thư giãn trước khi ngủ"},
    {"id": "qp-5", "text": "Đầu óc tôi đang rất bận rộn, tôi muốn tập chánh niệm"},
]


def get_quick_prompts() -> list[dict]:
    return _QUICK_PROMPTS
