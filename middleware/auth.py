# ============================================================
# middleware/auth.py — RapidAPI Authentication Middleware
# ============================================================

import hashlib
import hmac
import logging
import os
import re

from fastapi import Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from config import DEFAULT_PLAN, VALID_PLANS

load_dotenv()

logger = logging.getLogger(__name__)

RAPIDAPI_SECRET = (
    os.getenv("RAPIDAPI_PROXY_SECRET")
    or os.getenv("RAPIDAPI_SECRET")
)
REQUIRE_RAPIDAPI_PROXY_SECRET = os.getenv("REQUIRE_RAPIDAPI_PROXY_SECRET", "false").lower() == "true"

_SECRET_BYTES = RAPIDAPI_SECRET.encode("utf-8") if RAPIDAPI_SECRET else b""

_SAFE_ID_RE = re.compile(r'^[\x21-\x7E]{1,128}$')

_MAX_SECRET_LEN = 512
_PUBLIC_PATHS = {"/", "/health", "/plan", "/v1/plan"}
_PUBLIC_PREFIXES = ("/auth/", "/v1/auth/")


def _is_public_path(path: str) -> bool:
    return path in _PUBLIC_PATHS or any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


async def verify_rapidapi(request: Request, call_next):

    if request.method == "OPTIONS" or _is_public_path(request.url.path):
        logger.info(
            "rapidapi_auth bypass method=%s path=%s",
            request.method,
            request.url.path,
        )
        return await call_next(request)

    auth_header = request.headers.get("authorization", "").strip().lower()
    if auth_header.startswith("bearer "):
        logger.info(
            "rapidapi_auth bypass method=%s path=%s reason=bearer_token",
            request.method,
            request.url.path,
        )
        return await call_next(request)

    raw_secret   = request.headers.get("x-rapidapi-proxy-secret", "")
    raw_api_key  = request.headers.get("x-rapidapi-key", "")
    raw_host     = request.headers.get("x-rapidapi-host", "")
    raw_user_id  = request.headers.get("x-rapidapi-user", "")
    
    # 🔥 ONLY CHANGE IS HERE
    raw_plan     = request.headers.get("x-rapidapi-plan", DEFAULT_PLAN).lower()

    logger.info(
        "rapidapi_auth request path=%s method=%s has_proxy_secret=%s secret_len=%s has_key=%s has_host=%s has_user=%s plan=%s",
        request.url.path,
        request.method,
        bool(raw_secret),
        len(raw_secret),
        bool(raw_api_key),
        bool(raw_host),
        bool(raw_user_id),
        raw_plan,
    )

    if not raw_api_key:
        logger.warning(
            "rapidapi_auth reject reason=missing_standard_headers path=%s has_key=%s has_host=%s",
            request.url.path,
            bool(raw_api_key),
            bool(raw_host),
        )
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    should_validate_secret = REQUIRE_RAPIDAPI_PROXY_SECRET or (
        bool(raw_secret) and bool(RAPIDAPI_SECRET)
    )

    if should_validate_secret:
        if REQUIRE_RAPIDAPI_PROXY_SECRET and not raw_secret:
            logger.warning(
                "rapidapi_auth reject reason=missing_proxy_secret path=%s",
                request.url.path,
            )
            return JSONResponse(status_code=401, content={"error": "Unauthorized"})

        if len(raw_secret) > _MAX_SECRET_LEN:
            logger.warning(
                "rapidapi_auth reject reason=secret_too_long path=%s len=%s",
                request.url.path,
                len(raw_secret),
            )
            return JSONResponse(status_code=401, content={"error": "Unauthorized"})

        try:
            authorized = hmac.compare_digest(
                raw_secret.encode("utf-8"),
                _SECRET_BYTES,
            )
        except Exception:
            authorized = False

        if not authorized:
            logger.warning(
                "rapidapi_auth reject reason=secret_mismatch path=%s secret_len=%s configured_len=%s require_secret=%s",
                request.url.path,
                len(raw_secret),
                len(_SECRET_BYTES),
                REQUIRE_RAPIDAPI_PROXY_SECRET,
            )
            return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    plan = raw_plan if raw_plan in VALID_PLANS else DEFAULT_PLAN

    if _SAFE_ID_RE.match(raw_user_id):
        user_id = raw_user_id
    else:
        user_id = f"key-{hashlib.sha256(raw_api_key.encode('utf-8')).hexdigest()[:16]}"

    request.state.user_id = user_id
    request.state.plan    = plan

    logger.info(
        "rapidapi_auth accepted path=%s user_id=%s plan=%s",
        request.url.path,
        user_id,
        plan,
    )

    return await call_next(request)