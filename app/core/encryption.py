from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


def encrypt_text(plaintext: str) -> str:
    from app.core.config import settings
    key = settings.JOURNAL_ENCRYPTION_KEY
    return Fernet(key.encode()).encrypt(plaintext.encode()).decode()


def decrypt_text(ciphertext: str) -> str:
    from app.core.config import settings
    key = settings.JOURNAL_ENCRYPTION_KEY
    return Fernet(key.encode()).decrypt(ciphertext.encode()).decode()


class EncryptedText(TypeDecorator):
    """Transparent Fernet encryption on write, decryption on read.

    Key is read inside each method at call time — never at class/module level —
    so a missing env var in tests only fails when the column is actually accessed.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        from app.core.config import settings
        key = settings.JOURNAL_ENCRYPTION_KEY
        return Fernet(key.encode()).encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        from app.core.config import settings
        key = settings.JOURNAL_ENCRYPTION_KEY
        return Fernet(key.encode()).decrypt(value.encode()).decode()
