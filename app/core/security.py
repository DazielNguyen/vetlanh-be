from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

# cost factor 12 is explicit — passlib's default (12) can change across versions.
# Setting it explicitly ensures consistent hashing cost regardless of library updates.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> str:
    """Return the subject (email) from a valid token, or raise JWTError."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    # jwt.decode validates expiry automatically — never pass verify_exp=False
    return payload["sub"]
