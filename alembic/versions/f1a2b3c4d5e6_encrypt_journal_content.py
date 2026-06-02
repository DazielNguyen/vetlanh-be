"""encrypt journal content

Revision ID: f1a2b3c4d5e6
Revises: 6266dfa83a2b
Create Date: 2026-06-02 22:20:00.000000

DEPLOYMENT NOTE: Run this migration AFTER deploying the application code that
includes EncryptedText. Do NOT route traffic to journal endpoints until this
migration completes. The backup table (journal_entries_plaintext_backup) is left
in the DB after success — drop it manually once the migration is verified.
"""

from alembic import op
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text

revision = "f1a2b3c4d5e6"
down_revision = "6266dfa83a2b"
branch_labels = None
depends_on = None


def _get_key() -> bytes:
    import os
    key = os.environ.get("JOURNAL_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "JOURNAL_ENCRYPTION_KEY environment variable is not set. "
            "Cannot run journal encryption migration."
        )
    return key.encode()


def upgrade() -> None:
    key = _get_key()
    f = Fernet(key)
    conn = op.get_bind()

    # Backup plaintext before any modification — inside Alembic's ambient transaction
    conn.execute(text(
        "CREATE TABLE journal_entries_plaintext_backup AS SELECT * FROM journal_entries"
    ))

    rows = conn.execute(text("SELECT id, content FROM journal_entries")).fetchall()
    for row_id, content in rows:
        if content is None:
            continue
        try:
            # If decrypt succeeds, the row is already encrypted — skip it
            f.decrypt(content.encode())
        except InvalidToken:
            # Plaintext row — encrypt it
            encrypted = f.encrypt(content.encode()).decode()
            conn.execute(
                text("UPDATE journal_entries SET content = :c WHERE id = :id"),
                {"c": encrypted, "id": row_id},
            )


def downgrade() -> None:
    key = _get_key()
    f = Fernet(key)
    conn = op.get_bind()

    rows = conn.execute(text("SELECT id, content FROM journal_entries")).fetchall()
    for row_id, content in rows:
        if content is None:
            continue
        try:
            plaintext = f.decrypt(content.encode()).decode()
            conn.execute(
                text("UPDATE journal_entries SET content = :c WHERE id = :id"),
                {"c": plaintext, "id": row_id},
            )
        except InvalidToken:
            # Already plaintext — skip
            pass
