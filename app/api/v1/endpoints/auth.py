from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.schemas.auth import Token, UserRegister, UserLogin, UserResponse
from app.services.auth import login_user, register_user

router = APIRouter()


@router.post("/auth/register", response_model=UserResponse, status_code=201)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    return await register_user(db, body.email, body.password)


@router.post("/auth/login", response_model=Token)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    token = await login_user(db, body.email, body.password)
    return Token(access_token=token)
