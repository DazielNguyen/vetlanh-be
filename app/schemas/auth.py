from pydantic import BaseModel, EmailStr


class UserRegister(BaseModel):
    email: EmailStr
    password: str  # plain password — only in the request body, never stored


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool

    model_config = {"from_attributes": True}
    # hashed_password is intentionally absent — never expose it in any response
