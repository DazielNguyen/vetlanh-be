"""
Unit tests for app/core/security.py

These are pure unit tests — no DB, no HTTP, no async.
They run fast and test only the hashing/JWT logic in isolation.
"""

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_returns_bcrypt_string(self):
        h = hash_password("mypassword")
        # bcrypt hashes always start with $2b$ (version 2b)
        assert h.startswith("$2b$")

    def test_verify_correct_password(self):
        h = hash_password("mypassword")
        assert verify_password("mypassword", h) is True

    def test_verify_wrong_password(self):
        h = hash_password("mypassword")
        assert verify_password("wrongpass", h) is False

    def test_hash_is_unique_per_call(self):
        # bcrypt generates a random salt each time — same input → different hash
        h1 = hash_password("mypassword")
        h2 = hash_password("mypassword")
        assert h1 != h2


class TestJWT:
    def test_decode_returns_subject(self):
        token = create_access_token(subject="user@example.com")
        assert decode_access_token(token) == "user@example.com"

    def test_invalid_token_raises(self):
        from jose import JWTError
        import pytest

        with pytest.raises(JWTError):
            decode_access_token("not.a.valid.token")
