"""
Emotion & depression risk analysis for Vietnamese chat messages.

Uses the rule-based engine from app/ml/text_model.py by default (no extra
dependencies). When a fine-tuned PhoBERT checkpoint exists at
CHECKPOINT_DIR the full neural model is loaded instead.

The model is initialised once at first call and reused for the lifetime of
the process — never re-instantiated per request.
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any

from app.ml.preprocessing import clean_text
from app.ml.text_model import TextEmotionModel

logger = logging.getLogger(__name__)

# Sentiment bucket used by the existing `done` event field
_EMOTION_TO_SENTIMENT: dict[str, str] = {
    "happy":    "positive",
    "neutral":  "neutral",
    "sad":      "negative",
    "anxious":  "negative",
    "tired":    "negative",
    "angry":    "negative",
    "disgusted":"negative",
}


@lru_cache(maxsize=1)
def _get_model() -> TextEmotionModel:
    logger.info("Loading emotion model...")
    return TextEmotionModel.load()


def _run_predict(text: str) -> dict[str, Any]:
    model = _get_model()
    cleaned = clean_text(text)
    if not cleaned:
        return _empty_result()
    return model.predict(cleaned)


def _empty_result() -> dict[str, Any]:
    return {
        "emotion": {"label": "neutral", "confidence": 0.5, "all_probs": {}},
        "depression_risk": {"level": "none", "phq_estimate": 0.0, "confidence": 0.5, "all_probs": {}},
        "signals": [],
    }


async def analyze_emotion(text: str) -> dict[str, Any]:
    """Run emotion + depression risk analysis in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_predict, text)


def emotion_to_sentiment(emotion_label: str) -> str:
    """Map 7-class emotion label back to the legacy positive/neutral/negative bucket."""
    return _EMOTION_TO_SENTIMENT.get(emotion_label, "neutral")
