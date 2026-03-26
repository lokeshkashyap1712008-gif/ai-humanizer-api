# Word counting + monthly key helpers (timezone-safe)

from datetime import datetime, timedelta, timezone


def count_words(text: str) -> int:
    return len(text.split())


def get_month_key(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    return f"words:{user_id}:{now.year}-{now.month}"


def get_month_expiry() -> int:
    now = datetime.now(timezone.utc)

    # Move to next month safely
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

    return int(next_month.timestamp())
def count_words(text: str) -> int:
    return len(text.split())


def estimate_tokens(text: str) -> int:
    return int(len(text.split()) * 1.3)