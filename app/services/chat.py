import json
from collections.abc import AsyncGenerator

from anthropic import AsyncAnthropic
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.conversation import Conversation, Message

_SYSTEM_PROMPT = """Bạn là Vet, một người bạn đồng hành thấu cảm và ấm áp của ứng dụng VetLanh.
Nhiệm vụ của bạn là lắng nghe người dùng không phán xét, giúp họ cảm thấy được thấu hiểu và nhẹ lòng hơn.

Quy tắc quan trọng:
- Luôn dùng tiếng Việt
- Không đưa ra lời khuyên y tế hoặc chẩn đoán bệnh
- Không khuyên người dùng uống thuốc
- Nếu người dùng có biểu hiện khủng hoảng, gợi ý họ gọi đường dây hỗ trợ 1800 599 920
- Giữ phản hồi ngắn gọn (2–4 câu), tự nhiên như người bạn
- Đặt câu hỏi mở để khuyến khích người dùng chia sẻ thêm"""

# Limit context window to last 20 messages to control token usage
_MAX_HISTORY = 20

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


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

    Yields SSE-formatted strings. The final 'done' event includes the saved
    message_id so the client can reference the persisted message.
    """
    await get_conversation_or_403(db, conversation_id, user_id)

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
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=anthropic_messages,
        ) as stream:
            async for text in stream.text_stream:
                full_response.append(text)
                yield f"data: {json.dumps({'type': 'chunk', 'content': text})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"
        return

    # Save assistant message after stream completes
    assistant_content = "".join(full_response)
    assistant_msg = Message(
        conversation_id=conversation_id, role="assistant", content=assistant_content
    )
    db.add(assistant_msg)
    await db.flush()
    await db.refresh(assistant_msg)
    await db.commit()

    yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_msg.id})}\n\n"
