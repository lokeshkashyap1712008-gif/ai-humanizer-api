# Strong input sanitization + prompt injection protection
# No changes from original — logic was already correct

import re

BLOCK_PATTERNS = [
    r"ignore.*instructions",
    r"system\s+prompt",
    r"you\s+are\s+now",
    r"disregard.*previous",
    r"forget.*previous",
    r"new\s+instructions",
    r"act\s+as",
]


def sanitize_text(text: str) -> str:
    if not text:
        return ""

    # Remove null bytes
    text = text.replace("\x00", "")

    # Normalize line endings
    text = text.replace("\r\n", "\n")

    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Block known prompt injection patterns
    for pattern in BLOCK_PATTERNS:
        text = re.sub(pattern, "[removed]", text, flags=re.IGNORECASE)

    # Hard cap at 20,000 characters
    text = text[:20000]

    return text.strip()