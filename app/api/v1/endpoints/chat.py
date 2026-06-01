from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.chat import ConversationCreate, ConversationResponse, MessageResponse, SendMessageRequest
from app.services.chat import (
    create_conversation,
    get_messages,
    list_conversations,
    stream_chat,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def start_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await create_conversation(db, current_user.id, payload.title)
    await db.commit()
    return conv


@router.get("/conversations", response_model=list[ConversationResponse])
async def get_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_conversations(db, current_user.id)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_conversation_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_messages(db, conversation_id, current_user.id)


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: int,
    payload: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message and receive the AI response as an SSE stream.

    Response format:
      data: {"type": "chunk", "content": "..."}\n\n
        — one event per token during streaming

      data: {"type": "done", "message_id": 42, "exercise_card": {...}|null,
             "sentiment": "positive"|"neutral"|"negative",
             "suggest_checkin": false}\n\n
        — stream end; exercise_card is non-null when AI suggested a breathing exercise;
          suggest_checkin is true after 5+ consecutive negative messages

      data: {"type": "error", "detail": "..."}\n\n
        — on failure (message not persisted)
    """
    return StreamingResponse(
        stream_chat(db, conversation_id, current_user.id, payload.content),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
