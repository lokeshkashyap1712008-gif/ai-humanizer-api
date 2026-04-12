import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

import bcrypt
from fastapi import HTTPException, status

from config import VALID_PLANS
from utils.jwt_utils import issue_access_token
from utils.redis_client import get_redis

_BCRYPT_ROUNDS = 10
_MIN_PASSWORD_LEN = 8
_MAX_PASSWORD_LEN = 256
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_EMAIL_KEY_PREFIX = "auth:user:email:"
_USER_KEY_PREFIX = "auth:user:id:"


def _normalize_email(email: str) -> str:
    value = (email or "").strip().lower()
    if not _EMAIL_RE.match(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email format",
        )
    return value


def _validate_password(password: str) -> str:
    value = password or ""
    if not (_MIN_PASSWORD_LEN <= len(value) <= _MAX_PASSWORD_LEN):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be between 8 and 256 characters",
        )
    return value


def _email_key(email: str) -> str:
    digest = hashlib.sha256(email.encode("utf-8")).hexdigest()
    return f"{_EMAIL_KEY_PREFIX}{digest}"


def _user_key(user_id: str) -> str:
    return f"{_USER_KEY_PREFIX}{user_id}"


def _build_user_doc(user_id: str, email: str, password_hash: str, plan: str) -> dict:
    return {
        "user_id": user_id,
        "email": email,
        "password_hash": password_hash,
        "plan": plan,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _issue_token(user_id: str) -> str:
    try:
        return issue_access_token(user_id)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT is not configured",
        )


async def signup_user(email: str, password: str, plan: str = "free") -> dict:
    normalized_email = _normalize_email(email)
    validated_password = _validate_password(password)

    normalized_plan = (plan or "free").strip().lower()
    if normalized_plan not in VALID_PLANS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan",
        )

    redis = get_redis()

    email_key = _email_key(normalized_email)
    if await redis.get(email_key):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user_id = uuid.uuid4().hex
    password_hash = bcrypt.hashpw(
        validated_password.encode("utf-8"),
        bcrypt.gensalt(rounds=_BCRYPT_ROUNDS),
    ).decode("utf-8")

    created = await redis.setnx(email_key, user_id)
    if not created:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user_doc = _build_user_doc(user_id, normalized_email, password_hash, normalized_plan)
    await redis.set(_user_key(user_id), json.dumps(user_doc))

    token = _issue_token(user_id)

    return {
        "success": True,
        "token": token,
        "user": {
            "userId": user_id,
            "email": normalized_email,
            "plan": normalized_plan,
        },
    }


async def login_user(email: str, password: str) -> dict:
    normalized_email = _normalize_email(email)
    validated_password = _validate_password(password)

    redis = get_redis()
    user_id = await redis.get(_email_key(normalized_email))

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    raw_user_doc = await redis.get(_user_key(str(user_id)))
    if not raw_user_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    try:
        user_doc = json.loads(raw_user_doc)
    except (TypeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User storage error",
        )

    password_hash = (user_doc.get("password_hash") or "").encode("utf-8")
    if not password_hash or not bcrypt.checkpw(validated_password.encode("utf-8"), password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = _issue_token(str(user_doc.get("user_id")))

    return {
        "success": True,
        "token": token,
        "user": {
            "userId": user_doc.get("user_id"),
            "email": user_doc.get("email"),
            "plan": user_doc.get("plan", "free"),
        },
    }


async def get_user_by_id(user_id: str) -> dict:
    redis = get_redis()
    raw_user_doc = await redis.get(_user_key(user_id))

    if not raw_user_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    try:
        return json.loads(raw_user_doc)
    except (TypeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User storage error",
        )
