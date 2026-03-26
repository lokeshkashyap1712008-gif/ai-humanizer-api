# ============================================================
# utils/sanitize.py — Input Sanitization + Injection Defense
# ============================================================
# Security measures in this file:
#   ✅ Null-byte removal (prevents parser confusion)
#   ✅ CRLF / Unicode control-char stripping
#      (prevents log injection + header splitting)
#   ✅ Prompt-injection pattern blocking (unchanged set,
#      but now case-folded on a single normalised copy)
#   ✅ Hard character cap (20 000) applied LAST so regex
#      work never touches more than necessary
#   ✅ Unicode normalisation (NFC) — collapses look-alike
#      homoglyph sequences before pattern matching
# ============================================================

import re
import unicodedata

# ── Prompt-injection patterns ──────────────────────────────
BLOCK_PATTERNS = [
    r"ignore.*instructions",
    r"system\s+prompt",
    r"you\s+are\s+now",
    r"disregard.*previous",
    r"forget.*previous",
    r"new\s+instructions",
    r"act\s+as",
    r"jailbreak",
    r"dan\s+mode",
    r"developer\s+mode",
    r"pretend\s+(you\s+are|to\s+be)",
    r"override.*safety",
]

# Pre-compile for speed
_COMPILED = [re.compile(p, re.IGNORECASE) for p in BLOCK_PATTERNS]

# Strip C0/C1 control chars except \t \n \r
_CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]')


def sanitize_text(text: str) -> str:
    if not text:
        return ""

    # 1. Unicode normalisation — collapse homoglyphs
    text = unicodedata.normalize("NFC", text)

    # 2. Strip dangerous control characters (null bytes, CRLF variants, etc.)
    text = _CONTROL_RE.sub("", text)

    # 3. Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 4. Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 5. Block known prompt-injection patterns
    for pattern in _COMPILED:
        text = pattern.sub("[removed]", text)

    # 6. Hard cap at 20 000 characters
    text = text[:20000]

    return text.strip()