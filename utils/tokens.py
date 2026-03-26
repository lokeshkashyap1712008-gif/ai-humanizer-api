# Word counting + monthly key helpers (timezone-safe)
# ✅ FIX #11 — Removed duplicate count_words definition

from datetime import datetime, timezone


def count_words(text: str) -> int:
    """Return the number of whitespace-separated words in text."""
    return len(text.split())


def estimate_tokens(text: str) -> int:
    """Rough token estimate: words * 1.3 (matches typical English tokenization)."""
    return int(len(text.split()) * 1.3)


def get_month_key(user_id: str) -> str:
    """Redis key scoped to the current UTC month for a given user."""
    now = datetime.now(timezone.utc)
    return f"words:{user_id}:{now.year}-{now.month:02d}"


def get_month_expiry() -> int:
    """Unix timestamp of the start of next month (key TTL target)."""
    now = datetime.now(timezone.utc)
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return int(next_month.timestamp())