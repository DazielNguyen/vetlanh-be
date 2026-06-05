from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from app.core.config import settings

# bcrypt cost factor 12 — balances security and hashing speed (~250ms on modern hardware).
# passlib is intentionally NOT used: passlib 1.7.x is incompatible with bcrypt >= 4.x
# (passlib probes for wrap-bugs using a 100-byte password, which bcrypt 5.x rejects).
_BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    # bcrypt.hashpw expects bytes; encode to UTF-8 before hashing.
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> str:
    """Return the JWT subject (email for email/Google users, username for username users), or raise JWTError."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    # jwt.decode validates expiry automatically — never pass verify_exp=False
    return payload["sub"]
