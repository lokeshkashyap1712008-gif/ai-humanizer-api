# ============================================================
# utils/sanitize.py — Input Sanitization + Injection Defense
# ============================================================

import base64
import re
import unicodedata


class InjectionDetected(ValueError):
    """Raised when a high-confidence prompt injection pattern is found."""


# ── Constants ──────────────────────────────────────────────
MAX_INPUT_LENGTH = 20_000
MAX_B64_DECODE = 2000  # prevent heavy CPU decode attacks

# ── Regex (precompiled, optimized) ─────────────────────────
_WORD_BOUNDARY = r"(?:^|\b)"

HIGH_CONFIDENCE_PATTERNS = [
    rf"{_WORD_BOUNDARY}jailbreak\b",
    rf"{_WORD_BOUNDARY}dan\s+mode\b",
    rf"{_WORD_BOUNDARY}developer\s+mode\b",
    r"override.{0,50}safety",
    r"token\s+smuggl",
]

SOFT_PATTERNS = [
    r"ignore.{0,50}instructions",
    r"system\s+prompt",
    r"you\s+are\s+now",
    r"disregard.{0,50}previous",
    r"forget.{0,50}previous",
    r"new\s+instructions",
    r"act\s+as",
    r"pretend\s+(you\s+are|to\s+be)",
    r"repeat\s+(everything|all|above|prior)",
    r"what\s+(are|were)\s+your\s+instructions",
    r"reveal\s+(your\s+)?(system\s+)?prompt",
    r"(print|output|show|display)\s+(your\s+)?(system\s+)?prompt",
    r"bypass.{0,50}filter",
]

_HIGH = [re.compile(p, re.IGNORECASE) for p in HIGH_CONFIDENCE_PATTERNS]
_SOFT = [re.compile(p, re.IGNORECASE)]

_CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]')
_INVISIBLE_RE = re.compile(
    r'[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\u206a-\u206f\ufeff\u180e]'
)
_B64_RE = re.compile(r'[A-Za-z0-9+/]{40,}={0,2}')


# ── Base64 checker ─────────────────────────────────────────
def _check_b64_blob(match: re.Match) -> str:
    raw = match.group()

    # Prevent heavy decode attacks
    if len(raw) > MAX_B64_DECODE:
        return "[removed]"

    try:
        decoded = base64.b64decode(raw + "==", validate=False)
        decoded = decoded.decode("utf-8", errors="ignore")
        decoded = unicodedata.normalize("NFKC", decoded)

        for pattern in _HIGH:
            if pattern.search(decoded):
                raise InjectionDetected("Injection detected in base64 payload")

        for pattern in _SOFT:
            if pattern.search(decoded):
                return "[removed]"

    except InjectionDetected:
        raise
    except Exception:
        pass

    return raw


# ── Main Sanitizer ─────────────────────────────────────────
def sanitize_text(text: str) -> str:
    if not text:
        return ""

    # ── Hard cap early (performance protection) ─────────────
    text = text[:MAX_INPUT_LENGTH]

    # 1. Unicode normalization
    text = unicodedata.normalize("NFKC", text)

    # 2. Remove invisible chars
    text = _INVISIBLE_RE.sub("", text)

    # 3. Remove control chars
    text = _CONTROL_RE.sub("", text)

    # 4. Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 5. Collapse blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 6. Remove markdown code blocks
    text = re.sub(r'```.*?```', '[removed]', text, flags=re.DOTALL)
    text = re.sub(r'`[^`]{0,500}`', '[removed]', text)

    # 7. Base64 detection
    if len(text) > 40:
        text = _B64_RE.sub(_check_b64_blob, text)

    # 8. High-confidence detection (REJECT)
    for pattern in _HIGH:
        if pattern.search(text):
            raise InjectionDetected("Injection detected")

    # 9. Soft replacement
    for pattern in _SOFT:
        text = pattern.sub("[removed]", text)

    # 10. Cleanup repeated artifacts
    text = re.sub(r'(\[removed\]\s*){2,}', '[removed] ', text)

    return text.strip()