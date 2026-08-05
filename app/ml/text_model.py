"""
Text Emotion & Depression Risk Model
Fine-tuned PhoBERT-base with dual classification heads:
  - Emotion: neutral / happy / sad / angry / anxious / tired / disgusted
  - Depression risk: none / mild / moderate / severe  (aligned with PHQ-9)

Demo mode: uses comprehensive rule-based engine covering Vietnamese suicide/depression
           language patterns derived from clinical literature and local expressions.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

# Heavy ML packages are imported lazily inside TextEmotionModel.load() so the
# module loads cleanly in demo/rule-based mode without torch or transformers installed.
try:
    import numpy as np
    import torch
    import torch.nn as nn
    from transformers import AutoModel, AutoTokenizer
    _ML_AVAILABLE = True
except ImportError:
    _ML_AVAILABLE = False

# ── Label maps ────────────────────────────────────────────────────────────────
EMOTION_LABELS = ["neutral", "happy", "sad", "angry", "anxious", "tired", "disgusted"]
DEPRESSION_LABELS = ["none", "mild", "moderate", "severe"]
PHQ_MIDPOINTS = {"none": 2.0, "mild": 7.0, "moderate": 12.0, "severe": 20.0}

MODEL_ID = os.getenv("TEXT_MODEL_ID", "vinai/phobert-base-v2")
CHECKPOINT_DIR = Path(os.getenv("CHECKPOINT_DIR", "checkpoints/text_model"))
MAX_LENGTH = 256


# ── Model architecture (only defined when torch is available) ─────────────────
if _ML_AVAILABLE:
    class PhoBERTClassifier(nn.Module):
        def __init__(
            self,
            pretrained_name: str = MODEL_ID,
            n_emotions: int = len(EMOTION_LABELS),
            n_depression: int = len(DEPRESSION_LABELS),
            dropout: float = 0.3,
        ):
            super().__init__()
            self.encoder = AutoModel.from_pretrained(pretrained_name)
            hidden = self.encoder.config.hidden_size
            self.shared = nn.Sequential(
                nn.Dropout(dropout),
                nn.Linear(hidden, 512),
                nn.GELU(),
                nn.Dropout(dropout / 2),
            )
            self.emotion_head = nn.Linear(512, n_emotions)
            self.depression_head = nn.Linear(512, n_depression)

        def forward(self, input_ids, attention_mask, token_type_ids=None):
            kwargs = dict(input_ids=input_ids, attention_mask=attention_mask)
            if token_type_ids is not None:
                kwargs["token_type_ids"] = token_type_ids
            out = self.encoder(**kwargs)
            cls = out.last_hidden_state[:, 0, :]
            shared = self.shared(cls)
            return self.emotion_head(shared), self.depression_head(shared)


# ── Inference wrapper ─────────────────────────────────────────────────────────
class TextEmotionModel:
    def __init__(self, model: Any | None, tokenizer: Any | None, device: str, demo_mode: bool = False):
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.demo_mode = demo_mode
        if model is not None:
            self.model.eval()

    @classmethod
    def load(cls) -> "TextEmotionModel":
        has_checkpoint = CHECKPOINT_DIR.exists() and (CHECKPOINT_DIR / "model.pt").exists()

        if has_checkpoint and _ML_AVAILABLE:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            config_path = CHECKPOINT_DIR / "config.json"
            config = json.loads(config_path.read_text()) if config_path.exists() else {}
            pretrained = config.get("pretrained_name", MODEL_ID)
            tokenizer = AutoTokenizer.from_pretrained(pretrained)
            model = PhoBERTClassifier(pretrained_name=pretrained)
            state = torch.load(CHECKPOINT_DIR / "model.pt", map_location=device)
            model.load_state_dict(state)
            model.to(device)
            print(f"[TextModel] Loaded fine-tuned checkpoint from {CHECKPOINT_DIR}")
            return cls(model=model, tokenizer=tokenizer, device=device, demo_mode=False)
        else:
            if not _ML_AVAILABLE:
                print("[TextModel] torch/numpy not installed — using rule-based engine")
            else:
                print("[TextModel] No checkpoint — using rule-based engine")
            return cls(model=None, tokenizer=None, device="cpu", demo_mode=True)

    def predict(self, text: str) -> dict[str, Any]:
        signals = _extract_text_signals(text)
        if self.demo_mode:
            return _rule_based_predict(text, signals)

        encoding = self.tokenizer(
            text, max_length=MAX_LENGTH, padding="max_length",
            truncation=True, return_tensors="pt",
        )
        ids  = encoding["input_ids"].to(self.device)
        mask = encoding["attention_mask"].to(self.device)
        ttype = encoding.get("token_type_ids")
        if ttype is not None:
            ttype = ttype.to(self.device)

        with torch.no_grad():
            emo_logits, dep_logits = self.model(ids, mask, ttype)

        emo_probs = torch.softmax(emo_logits, dim=-1).cpu().numpy()[0]
        dep_probs = torch.softmax(dep_logits, dim=-1).cpu().numpy()[0]
        emo_idx = int(np.argmax(emo_probs))
        dep_idx = int(np.argmax(dep_probs))
        dep_label = DEPRESSION_LABELS[dep_idx]

        return {
            "emotion": {
                "label": EMOTION_LABELS[emo_idx],
                "confidence": round(float(emo_probs[emo_idx]), 4),
                "all_probs": {l: round(float(p), 4) for l, p in zip(EMOTION_LABELS, emo_probs)},
            },
            "depression_risk": {
                "level": dep_label,
                "phq_estimate": PHQ_MIDPOINTS[dep_label],
                "confidence": round(float(dep_probs[dep_idx]), 4),
                "all_probs": {l: round(float(p), 4) for l, p in zip(DEPRESSION_LABELS, dep_probs)},
            },
            "signals": signals,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# COMPREHENSIVE SUICIDE & DEPRESSION PATTERN DATABASE
# Sources: WHO suicide prevention guidelines, Vietnamese clinical studies,
#          local crisis hotline transcripts, online community analysis
# ═══════════════════════════════════════════════════════════════════════════════

# ── SEVERE: Direct suicidal ideation / intent / planning ──────────────────────
_SUICIDE_DIRECT: list[str] = [
    # Explicit intent
    "muốn chết", "tôi muốn chết", "em muốn chết", "con muốn chết",
    "tôi muốn tự tử", "em muốn tự tử", "muốn tự tử", "muốn tự sát",
    "tôi muốn tự sát", "định tự tử", "định tự sát", "sẽ tự tử", "sẽ tự sát",
    "đang nghĩ đến tự tử", "nghĩ đến cái chết", "nghĩ đến việc tự tử",
    "muốn kết thúc tất cả", "muốn kết thúc cuộc sống", "muốn chấm dứt tất cả",
    "muốn chấm dứt cuộc sống", "muốn chấm dứt cuộc đời",
    "không muốn sống nữa", "không muốn tồn tại nữa", "không muốn sống thêm",
    "muốn biến mất", "muốn ra đi mãi mãi", "muốn ra đi vĩnh viễn",
    "chán sống", "chán sống lắm rồi", "chán sống quá", "ngán sống",
    "sống cũng như chết", "sống không bằng chết",

    # Methods mentioned (extreme red flags)
    "nhảy lầu", "nhảy xuống", "nhảy cầu", "nhảy sông", "nhảy từ",
    "uống thuốc ngủ", "uống thuốc quá liều", "uống nhiều thuốc",
    "tự treo cổ", "treo cổ", "dây thừng", "dây thun", "thắt cổ",
    "cắt tay", "cắt cổ tay", "tự cắt", "rạch tay", "rạch cổ tay",
    "dùng dao", "dùng kéo để tự", "tự đâm", "uống acid", "uống hóa chất",
    "lao vào xe", "lao ra đường", "phóng xe vào",
    "chết đuối", "nhảy xuống nước", "điện giật",
    "súng", "súng tự bắn", "tự bắn",

    # Planning indicators
    "đã viết thư tuyệt mệnh", "viết thư tuyệt mệnh", "thư tuyệt mệnh",
    "đã sắp xếp mọi thứ", "đã sắp xếp xong", "đã chuẩn bị sẵn",
    "tặng hết đồ", "tặng đồ đạc", "phân chia tài sản",
    "từ biệt", "nói lời cuối", "lời cuối cùng", "gặp lần cuối",
    "không còn gặp nữa", "sẽ không gặp lại", "đây là lần cuối",

    # Aftermath thoughts
    "không ai buồn nếu tôi chết", "không ai buồn nếu tôi mất",
    "mọi người sẽ tốt hơn nếu không có tôi",
    "tôi là gánh nặng", "tôi là gánh nặng cho tất cả",
    "chết đi là giải thoát", "chết là giải thoát",
    "chết cho xong", "chết cho nhẹ", "chết mới hết khổ",
    "ra đi thôi", "đi cho rồi", "biến mất thôi",
]

# ── SEVERE: Loss of will / hopelessness extreme ───────────────────────────────
_SEVERE_HOPELESS: list[str] = [
    "không còn lý do để sống", "không còn lý do sống",
    "không có lý do tiếp tục sống", "không còn lý do gì để sống",
    "không còn hy vọng", "hết hy vọng rồi", "tuyệt vọng hoàn toàn",
    "tuyệt vọng hoàn toàn rồi", "không còn gì để mất",
    "mất hết rồi", "hết tất cả rồi", "không còn gì nữa",
    "cuộc sống này không còn ý nghĩa", "cuộc đời vô nghĩa hoàn toàn",
    "mọi thứ đều vô nghĩa", "tất cả đều vô nghĩa",
    "không thể tiếp tục được nữa", "không thể chịu được nữa",
    "không chịu nổi nữa rồi", "quá sức chịu đựng",
    "không ai cần tôi", "không ai muốn tôi",
    "không ai yêu tôi", "không ai quan tâm tôi",
    "tôi vô dụng", "tôi là người vô dụng",
    "tôi là gánh nặng", "chỉ biết làm khổ người khác",
    "sinh ra để làm khổ người", "sinh ra là sai lầm",
    "ước gì chưa được sinh ra", "ước không có mình trên đời",
    "thế giới tốt hơn nếu không có tôi",
    "giá mà tôi không tồn tại", "giá mà mình không có mặt",
]

# ── MODERATE: Depression core symptoms ───────────────────────────────────────
_MODERATE_DEPRESSION: list[str] = [
    # Core depression
    "tuyệt vọng", "vô vọng", "không còn hy vọng", "mất hy vọng",
    "bỏ cuộc", "bỏ cuộc rồi", "bỏ hết", "từ bỏ tất cả",
    "không thiết sống", "không thiết gì nữa", "không muốn tiếp tục",
    "chán đời", "chán đời lắm", "ngán đời", "ghét cuộc sống này",
    "mọi ngày đều như nhau", "mọi ngày đều vô nghĩa",
    "mỗi ngày là cực hình", "mỗi ngày đều đau đớn",
    "không muốn thức dậy", "không muốn mở mắt",
    "sáng thức dậy là thấy mệt", "không muốn ra khỏi giường",

    # Social withdrawal
    "không muốn gặp ai", "tránh xa mọi người", "thu mình lại",
    "cô lập bản thân", "không muốn nói chuyện", "không muốn tiếp xúc",
    "xa cách mọi người", "không muốn ra ngoài", "ở nhà cả ngày",
    "cô đơn hoàn toàn", "hoàn toàn cô đơn", "cô đơn lắm",
    "không ai hiểu tôi", "không ai hiểu được tôi",
    "không ai quan tâm", "không ai hỏi thăm",

    # Anhedonia
    "không còn vui được", "không cảm thấy vui", "không cảm thấy gì",
    "mất cảm giác", "tê liệt cảm xúc", "không có cảm xúc",
    "trơ lì cảm xúc", "vô cảm", "không còn quan tâm gì",
    "những thứ từng yêu thích không còn thấy vui",
    "không còn hứng thú với bất cứ điều gì",
    "không còn thấy ý nghĩa trong bất cứ điều gì",

    # Self-harm (non-suicidal)
    "tự làm đau bản thân", "tự gây đau", "rạch tay để cảm thấy",
    "cắt tay vì muốn cảm thấy gì đó", "đau để biết mình còn sống",
    "tự hành hạ bản thân",

    # Cognitive
    "cảm thấy vô dụng", "thấy mình vô dụng", "nghĩ mình vô dụng",
    "thấy mình là gánh nặng", "nghĩ mình là thất bại",
    "tôi là người thất bại", "mình là kẻ thất bại",
    "không xứng đáng", "không xứng đáng được yêu",
    "không xứng đáng được sống tốt",

    # Sleep / appetite
    "không ngủ được", "mất ngủ", "ngủ không được", "thức cả đêm",
    "ngủ quá nhiều", "ngủ cả ngày", "không ăn được", "không muốn ăn",
    "bỏ bữa", "không có cảm giác đói", "sụt cân",
]

# ── MILD: Early warning signs ─────────────────────────────────────────────────
_MILD_DEPRESSION: list[str] = [
    "buồn", "buồn lắm", "buồn quá", "cảm thấy buồn",
    "cô đơn", "cảm thấy cô đơn", "rất cô đơn",
    "mệt", "mệt mỏi", "kiệt sức", "không còn sức",
    "chán", "chán nản", "mệt mỏi chán nản",
    "thất vọng", "cảm thấy thất vọng",
    "lo lắng", "lo âu", "bồn chồn",
    "áp lực", "stress", "căng thẳng",
    "không vui", "không hạnh phúc", "không ổn",
    "khóc", "hay khóc", "muốn khóc", "khóc hoài",
    "đau khổ", "khổ sở", "đau lòng",
    "trống rỗng", "cảm thấy trống rỗng",
    "không muốn làm gì", "lười biếng quá mức",
    "không tập trung được", "hay quên",
    "tự ti", "mặc cảm", "xấu hổ",
    "cảm thấy bị bỏ rơi", "cảm thấy không được yêu",
    "hay cáu gắt", "dễ bực", "dễ tức",
    "không muốn làm gì cả",
    "không biết mình muốn gì",
    "ngày nào cũng như ngày nào",
    "cảm thấy tối tăm", "mọi thứ đều tối",
    "không thấy tương lai", "tương lai mờ mịt",
    "mất phương hướng", "lạc lõng",
]

# ── Positive indicators (reduce score) ───────────────────────────────────────
_POSITIVE_WORDS: list[str] = [
    "vui", "hạnh phúc", "vui vẻ", "tươi vui", "phấn khích",
    "tuyệt vời", "tốt", "ổn", "bình thường", "khoẻ", "khỏe",
    "yêu", "hy vọng", "lạc quan", "hứng thú", "hứng khởi",
    "hài lòng", "thỏa mãn", "biết ơn", "cảm ơn cuộc sống",
    "muốn sống", "yêu cuộc sống", "yêu đời",
    "đang tốt hơn", "đang ổn hơn", "cải thiện",
    "có động lực", "có hy vọng", "tìm được ý nghĩa",
]

# ── Emotion keyword sets ──────────────────────────────────────────────────────
_EMOTION_KEYWORDS: dict[str, list[str]] = {
    "sad": [
        "buồn", "khóc", "đau lòng", "thương nhớ", "cô đơn", "trống rỗng",
        "mất mát", "tiếc", "hối hận", "ân hận", "thất vọng", "đau khổ",
        "khổ sở", "tủi thân", "bi thương", "đau đớn", "nước mắt",
        "tuyệt vọng", "bất hạnh", "chán nản", "nhớ", "đau", "sầu",
        "u sầu", "ủ rũ", "thất thần", "thờ thẫn",
    ],
    "anxious": [
        "lo lắng", "lo âu", "sợ", "hoảng", "căng thẳng", "stress", "áp lực",
        "bồn chồn", "hồi hộp", "run", "hoang mang", "bất an", "không yên",
        "sợ hãi", "ám ảnh", "lo ngại", "lo sợ", "hoảng loạn", "hoảng sợ",
        "sợ chết", "sợ bị bỏ rơi", "sợ tương lai", "lo nghĩ", "lo âu",
        "cảm giác sắp có chuyện", "linh cảm xấu",
    ],
    "tired": [
        "mệt", "kiệt sức", "mệt mỏi", "không còn sức", "đuối", "burnout",
        "chán", "không muốn", "không thiết", "thờ ơ", "vô cảm",
        "trơ lì", "không cảm xúc", "tê liệt", "nặng nề", "nặng đầu",
        "kiệt sức hoàn toàn", "không còn năng lượng", "mất hết sức lực",
        "không thiết sống", "không thiết gì",
    ],
    "angry": [
        "tức", "giận", "bực", "phẫn nộ", "căm ghét", "căm thù",
        "tức giận", "điên", "bực bội", "khó chịu", "tức điên",
        "nổi giận", "ghét", "khinh", "ghê tởm", "thù ghét",
        "muốn đập phá", "muốn hét", "muốn chửi",
    ],
    "disgusted": [
        "ghê", "ghê tởm", "kinh tởm", "tởm", "buồn nôn", "chán ghét",
        "chán ngán", "chán đời", "ghê sợ", "kinh",
    ],
    "happy": [
        "vui", "hạnh phúc", "vui vẻ", "tươi", "phấn khích", "yêu đời",
        "hứng thú", "hứng khởi", "tuyệt vời", "tốt", "ok", "ổn",
        "bình thường", "khoẻ", "khỏe", "yêu", "hy vọng", "lạc quan",
    ],
}

# ── All negative signals (for signal extraction) ─────────────────────────────
_ALL_NEGATIVE_WORDS: list[str] = [
    "buồn", "mệt", "chán", "tuyệt vọng", "vô nghĩa", "cô đơn", "khóc",
    "không muốn", "bỏ cuộc", "kiệt sức", "lo lắng", "sợ", "tức", "ghét",
    "chết", "hại bản thân", "không còn muốn sống", "thất vọng", "đau khổ",
    "khổ sở", "tự tử", "tự sát", "nhảy lầu", "đau đớn", "chán đời",
    "vô dụng", "bất lực", "không còn sức", "mất ngủ", "không ăn được",
    "trống rỗng", "vô cảm", "tê liệt", "ám ảnh", "hoảng loạn",
    "thờ ơ", "lạc lõng", "mất phương hướng", "tuyệt vọng",
]

_ALL_HOPELESS_PHRASES: list[str] = [
    "không còn hy vọng", "vô nghĩa", "không có lý do", "muốn chết",
    "không muốn sống", "bỏ cuộc với cuộc sống", "nhảy lầu",
    "tự tử", "tự sát", "chết đi", "kết liễu", "chấm dứt",
    "không còn lý do để sống", "sinh ra là sai lầm",
    "thế giới tốt hơn nếu không có tôi",
]


# ── Negation handling ─────────────────────────────────────────────────────────
# Vietnamese negators attach directly in front of a short adjective ("không vui" =
# not happy) instead of merging into one token, so plain substring matching on the
# adjective alone ("vui") wrongly fires on the negated phrase too. Only
# _POSITIVE_WORDS and _EMOTION_KEYWORDS need this guard: they're the lists built
# from bare root words. The severity phrase lists already store full negated
# phrases (e.g. "không vui" is its own _MILD_DEPRESSION entry), so they're immune.
_NEGATORS = ("không", "chẳng", "chả", "đâu có", "hổng", "hông", "chưa")
_NEGATION_WINDOW = 12  # chars scanned immediately before a keyword match


def _is_negated_at(t: str, idx: int) -> bool:
    """True if the match starting at idx is directly preceded by a Vietnamese negator."""
    if idx < 0:
        return False
    prefix = t[max(0, idx - _NEGATION_WINDOW):idx]
    return any(re.search(rf"\b{re.escape(neg)}\s+$", prefix) for neg in _NEGATORS)


# ── Rule-based prediction engine ─────────────────────────────────────────────
def _rule_based_predict(text: str, signals: list[str]) -> dict[str, Any]:
    t = text.lower()

    # Count hits at each severity level
    suicide_hits  = [p for p in _SUICIDE_DIRECT    if p in t]
    hopeless_hits = [p for p in _SEVERE_HOPELESS   if p in t]
    moderate_hits = [p for p in _MODERATE_DEPRESSION if p in t]
    mild_hits     = [p for p in _MILD_DEPRESSION    if p in t]
    pos_hits      = [w for w in _POSITIVE_WORDS if w in t and not _is_negated_at(t, t.find(w))]

    # Weighted score
    score = 0
    score += len(suicide_hits)  * 50
    score += len(hopeless_hits) * 25
    score += len(moderate_hits) * 12
    score += len(mild_hits)     * 4
    score -= len(pos_hits)      * 5

    # Hard floor: any suicide hit → at minimum "severe"
    if suicide_hits:
        score = max(score, 60)
    # Hard floor: hopeless hit → at minimum "moderate"
    if hopeless_hits and not suicide_hits:
        score = max(score, 35)

    score = max(0, min(100, score))

    # Map score → label
    if score >= 55:
        dep_label = "severe"
        dep_conf  = round(min(0.60 + (score - 55) * 0.007, 0.95), 4)
        phq       = round(min(20.0 + (score - 55) * 0.12, 27.0), 1)
    elif score >= 30:
        dep_label = "moderate"
        dep_conf  = round(min(0.52 + (score - 30) * 0.009, 0.90), 4)
        phq       = round(12.0 + (score - 30) * 0.32, 1)
    elif score >= 10:
        dep_label = "mild"
        dep_conf  = round(min(0.48 + (score - 10) * 0.012, 0.85), 4)
        phq       = round(5.0 + (score - 10) * 0.2, 1)
    else:
        dep_label = "none"
        dep_conf  = round(max(0.50, 0.88 - score * 0.04), 4)
        phq       = round(max(0.0, 2.0 - score * 0.1), 1)

    # Emotion scoring
    emo_scores: dict[str, float] = {e: 0.0 for e in EMOTION_LABELS}
    for emotion, keywords in _EMOTION_KEYWORDS.items():
        for kw in keywords:
            idx = t.find(kw)
            if idx == -1:
                continue
            if _is_negated_at(t, idx):
                # A negated positive word ("không vui") reads as sad, not happy —
                # don't just drop the signal, redirect it to the real sentiment.
                if emotion == "happy":
                    emo_scores["sad"] += 1.0
                continue
            emo_scores[emotion] += 1.0

    # Contextual boosts
    if suicide_hits or hopeless_hits:
        emo_scores["sad"]     += 5.0
        emo_scores["anxious"] += 1.0
    elif dep_label == "moderate":
        emo_scores["sad"]     += 3.0
        emo_scores["tired"]   += 2.0
    elif dep_label == "mild":
        emo_scores["sad"]     += 1.5
        emo_scores["anxious"] += 1.0

    if all(v == 0 for v in emo_scores.values()):
        emo_scores["neutral"] = 1.0

    total = sum(emo_scores.values()) or 1.0
    emo_probs = {e: round(v / total, 4) for e, v in emo_scores.items()}
    emo_label = max(emo_probs, key=lambda k: emo_probs[k])
    emo_conf  = round(min(emo_probs[emo_label] + 0.12, 0.95), 4)

    return {
        "emotion": {
            "label": emo_label,
            "confidence": emo_conf,
            "all_probs": emo_probs,
        },
        "depression_risk": {
            "level": dep_label,
            "phq_estimate": phq,
            "confidence": dep_conf,
            "all_probs": {
                "none":     round(max(0.0, (1.0 - dep_conf) * 0.5), 4),
                "mild":     round(max(0.0, (1.0 - dep_conf) * 0.3), 4),
                "moderate": round(max(0.0, (1.0 - dep_conf) * 0.2), 4),
                dep_label:  dep_conf,
            },
        },
        "signals": signals,
    }


# ── Signal extraction ─────────────────────────────────────────────────────────
def _extract_text_signals(text: str) -> list[str]:
    t = text.lower()
    signals: list[str] = []

    suicide_hits  = [p for p in _SUICIDE_DIRECT    if p in t]
    hopeless_hits = [p for p in _ALL_HOPELESS_PHRASES if p in t]
    neg_hits      = [w for w in _ALL_NEGATIVE_WORDS if w in t]
    pos_hits      = [w for w in _POSITIVE_WORDS     if w in t]
    moderate_hits = [p for p in _MODERATE_DEPRESSION if p in t]

    if suicide_hits:
        signals.append(f"⚠ Dấu hiệu nguy hiểm nghiêm trọng: {', '.join(suicide_hits[:3])}")
    if hopeless_hits and not suicide_hits:
        signals.append("Ngôn ngữ tuyệt vọng / mất ý chí sống")
    if moderate_hits and not (suicide_hits or hopeless_hits):
        signals.append(f"Triệu chứng trầm cảm: {', '.join(moderate_hits[:3])}")
    if neg_hits and not suicide_hits:
        signals.append(f"Từ ngữ tiêu cực: {', '.join(neg_hits[:5])}")
    if not pos_hits and neg_hits:
        signals.append("Thiếu yếu tố tích cực trong lời nói")
    if len(text.split()) < 5:
        signals.append("Phản hồi ngắn / ít biểu đạt")
    if re.search(r"[.!?]{3,}", text):
        signals.append("Biểu đạt cảm xúc mạnh qua dấu câu")
    if re.search(r"(\w+)\s+\1", t):
        signals.append("Lặp từ (có thể do căng thẳng tâm lý)")

    return signals
