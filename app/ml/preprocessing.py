"""
Vietnamese text preprocessing utilities.
"""
from __future__ import annotations

import re
import unicodedata


# ── Normalization ──────────────────────────────────────────────────────────────
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)
_REPEATED_PUNCT = re.compile(r"([!?.]{3,})")
_MULTI_SPACE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """
    Clean and normalise Vietnamese text for the model.
    Steps:
      1. Unicode NFC normalisation
      2. Remove URLs
      3. Convert emoji to space (preserve sentence length shape)
      4. Compress repeated punctuation to 3 chars max
      5. Strip extra whitespace
    """
    if not text or not text.strip():
        return ""

    # NFC normalisation (important for Vietnamese diacritics)
    text = unicodedata.normalize("NFC", text)

    # Remove URLs
    text = _URL_RE.sub(" ", text)

    # Emoji → space
    text = _EMOJI_RE.sub(" ", text)

    # Normalise repeated punctuation (e.g. "!!!!!!" → "!!!")
    text = _REPEATED_PUNCT.sub(r"\1\1\1", text)

    # Collapse whitespace
    text = _MULTI_SPACE.sub(" ", text).strip()

    return text


def split_sentences(text: str) -> list[str]:
    """Rough sentence splitter for Vietnamese text."""
    text = clean_text(text)
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def truncate_text(text: str, max_chars: int = 1000) -> str:
    """Truncate to last full sentence within max_chars."""
    if len(text) <= max_chars:
        return text
    sentences = split_sentences(text[:max_chars])
    return " ".join(sentences[:-1]) if len(sentences) > 1 else text[:max_chars]
