from pydantic import BaseModel, EmailStr, field_validator


class UserRegister(BaseModel):
    email: EmailStr
    password: str  # plain password — only in the request body, never stored

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        # Enforce ≥ 8 chars at the schema layer so the error is a 422 (validation),
        # not a 400 or a silent accept-and-store.
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    """Generic single-message response — used for verification, resend, etc."""

    message: str


class ResendRequest(BaseModel):
    email: EmailStr


class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool
    is_verified: bool

    model_config = {"from_attributes": True}
    # hashed_password and verification_token are intentionally absent
