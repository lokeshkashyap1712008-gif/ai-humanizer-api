from datetime import datetime, timedelta, timezone
import os

import jwt


def _get_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


JWT_ALGORITHM = (os.getenv("JWT_ALGORITHM", "HS256") or "HS256").strip()
JWT_EXPIRES_IN_HOURS = _get_int_env("JWT_EXPIRES_IN_HOURS", 24)


# Security: Minimum 32 bytes for HS256
_MIN_JWT_SECRET_LEN = 32


def get_jwt_secret() -> str:
    secret = (os.getenv("JWT_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("Missing JWT_SECRET configuration")
    if len(secret) < _MIN_JWT_SECRET_LEN:
        raise RuntimeError(
            f"JWT_SECRET must be at least {_MIN_JWT_SECRET_LEN} characters long"
        )
    # Validate algorithm is secure
    if JWT_ALGORITHM not in {"HS256", "HS384", "HS512"}:
        raise RuntimeError(f"Unsupported JWT algorithm: {JWT_ALGORITHM}")
    return secret


def issue_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "userId": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=JWT_EXPIRES_IN_HOURS)).timestamp()),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    # Explicitly only allow our configured algorithm to prevent algorithm confusion attacks
    return jwt.decode(
        token,
        get_jwt_secret(),
        algorithms=[JWT_ALGORITHM],
        options={"verify_signature": True, "verify_exp": True}
    )
