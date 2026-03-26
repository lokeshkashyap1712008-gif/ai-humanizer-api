# ============================================================
# utils/sanitize.py — Input Sanitization + Injection Defense
# ============================================================
# Security measures in this file:
#   ✅ NFKC normalisation — collapses fullwidth/homoglyph
#      characters (e.g. Ａct ａs → Act as) before matching
#   ✅ Null-byte + C0/C1 control-char removal
#      (prevents log injection + header splitting)
#   ✅ Markdown code-fence stripping — prevents hiding
#      injection payloads inside triple-backtick blocks
#   ✅ Base64 blob detection + decode-and-check — prevents
#      encoding injection payloads in base64 to bypass regex
#   ✅ Zero-width / invisible Unicode character removal —
#      prevents splitting injection keywords with invisible
#      chars (e.g. "ig\u200bnore" bypasses naive regex)
#   ✅ FIX: Two-tier injection handling — HIGH_CONFIDENCE
#      patterns (jailbreak, dan mode, developer mode,
#      override safety) raise InjectionError immediately,
#      returning a 400 to the caller. Softer patterns that
#      can appear legitimately (e.g. "act as" in fiction)
#      are still substituted with [removed] and the request
#      continues. Previously ALL patterns were substituted,
#      meaning a clear jailbreak attempt would reach Claude
#      with its keywords replaced but its surrounding
#      instruction structure intact.
#   ✅ Hard character cap (20 000) applied last
#   ✅ Structural delimiter appended by caller in ai_router —
#      "ABOVE IS UNTRUSTED USER TEXT" guard in system prompt
# ============================================================

import base64
import re
import unicodedata


class InjectionDetected(ValueError):
    """
    Raised when a high-confidence prompt injection pattern is found.
    Callers should return HTTP 400 — do not forward the text to the AI.
    """


# ── High-confidence patterns → REJECT immediately ──────────
# These phrases have no plausible legitimate use in a humanization
# request. Any occurrence, even after normalization, is treated as
# a deliberate injection attempt and results in an InjectionDetected
# exception rather than a substitution. The request is rejected with
# 400 before the text reaches Claude.
HIGH_CONFIDENCE_PATTERNS = [
    r"jailbreak",
    r"dan\s+mode",
    r"developer\s+mode",
    r"override.*safety",
    r"token\s+smuggl",
]

_HIGH_CONFIDENCE_COMPILED = [
    re.compile(p, re.IGNORECASE | re.DOTALL) for p in HIGH_CONFIDENCE_PATTERNS
]

# ── Softer patterns → substitute with [removed] and continue ─
# These can appear in legitimate creative or academic text
# (e.g. "act as a narrator", "you are now reading about...").
# Replacing the keywords degrades any injected payload while
# preserving enough of the surrounding text to be humanized.
SOFT_PATTERNS = [
    r"ignore.*instructions",
    r"system\s+prompt",
    r"you\s+are\s+now",
    r"disregard.*previous",
    r"forget.*previous",
    r"new\s+instructions",
    r"act\s+as",
    r"pretend\s+(you\s+are|to\s+be)",
    r"repeat\s+(everything|all|above|prior)",
    r"what\s+(are|were)\s+your\s+instructions",
    r"reveal\s+(your\s+)?(system\s+)?prompt",
    r"(print|output|show|display)\s+(your\s+)?(system\s+)?prompt",
    r"bypass.*filter",
]

_SOFT_COMPILED = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in SOFT_PATTERNS]

# All compiled patterns — used by the base64 blob checker
_ALL_COMPILED = _HIGH_CONFIDENCE_COMPILED + _SOFT_COMPILED

# Strip C0/C1 control chars except \t \n \r
_CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]')

# Zero-width and invisible Unicode characters
_INVISIBLE_RE = re.compile(
    r'[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\u206a-\u206f\ufeff\u180e]'
)

# Base64 blobs: at least 40 chars of base64 alphabet
_B64_RE = re.compile(r'[A-Za-z0-9+/]{40,}={0,2}')


def _check_b64_blob(match: re.Match) -> str:
    """
    Decode a base64-looking blob and check it for injection patterns.
    High-confidence matches raise InjectionDetected.
    Soft matches return [removed].
    Benign blobs are left untouched.
    """
    raw = match.group()
    try:
        decoded = base64.b64decode(raw + "==").decode("utf-8", errors="ignore")
        decoded = unicodedata.normalize("NFKC", decoded)

        for pattern in _HIGH_CONFIDENCE_COMPILED:
            if pattern.search(decoded):
                raise InjectionDetected(
                    "High-confidence injection pattern detected in base64 payload"
                )

        for pattern in _SOFT_COMPILED:
            if pattern.search(decoded):
                return "[removed]"
    except InjectionDetected:
        raise
    except Exception:
        pass
    return raw


def sanitize_text(text: str) -> str:
    """
    Sanitize user-supplied text before forwarding to the AI.

    Raises:
        InjectionDetected: if a high-confidence prompt injection keyword is
            found after normalization. Callers should return HTTP 400.

    Returns:
        Sanitized text string (never empty if input was non-empty;
        check the return value and reject if blank after stripping).
    """
    if not text:
        return ""

    # 1. NFKC normalisation — collapses fullwidth homoglyphs
    text = unicodedata.normalize("NFKC", text)

    # 2. Remove zero-width / invisible chars
    text = _INVISIBLE_RE.sub("", text)

    # 3. Strip dangerous control characters
    text = _CONTROL_RE.sub("", text)

    # 4. Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 5. Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 6. Strip markdown code fences
    text = re.sub(r'```.*?```', '[removed]', text, flags=re.DOTALL)
    text = re.sub(r'`[^`]{0,500}`', '[removed]', text)

    # 7. Decode and inspect base64 blobs
    #    (may raise InjectionDetected for high-confidence hits)
    text = _B64_RE.sub(_check_b64_blob, text)

    # 8. FIX: Two-tier pattern matching
    #    High-confidence patterns → reject immediately
    for pattern in _HIGH_CONFIDENCE_COMPILED:
        if pattern.search(text):
            raise InjectionDetected(
                "High-confidence injection pattern detected in user text"
            )

    #    Soft patterns → substitute and continue
    for pattern in _SOFT_COMPILED:
        text = pattern.sub("[removed]", text)

    # 9. Hard cap at 20 000 characters
    text = text[:20_000]

    return text.strip()