import hashlib
import hmac
import logging
import os
import re

from fastapi import Request
from fastapi.responses import JSONResponse

from config import DEFAULT_PLAN, VALID_PLANS

logger = logging.getLogger(__name__)

_SAFE_ID_RE = re.compile(r"^[\x21-\x7E]{1,128}$")
_TRUE_VALUES = {"1", "true", "yes", "on"}

# Public routes
_PUBLIC_PATHS = {"/", "/health", "/plan", "/v1/plan"}
_PUBLIC_PREFIXES = ()

_EXPECTED_PROXY_SECRET = (
    os.getenv("RAPIDAPI_PROXY_SECRET", "").strip()
    or os.getenv("RAPIDAPI_SECRET", "").strip()
)
_REQUIRE_PROXY_SECRET = (
    os.getenv("REQUIRE_RAPIDAPI_PROXY_SECRET", "true").strip().lower() in _TRUE_VALUES
)


def _is_public_path(path: str) -> bool:
    return path in _PUBLIC_PATHS or any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


def _unauthorized() -> JSONResponse:
    return JSONResponse(status_code=401, content={"error": "Unauthorized"})


async def verify_rapidapi(request: Request, call_next):
    if request.method == "OPTIONS" or _is_public_path(request.url.path):
        return await call_next(request)

    api_key = (request.headers.get("x-rapidapi-key") or "").strip()
    proxy_secret = (request.headers.get("x-rapidapi-proxy-secret") or "").strip()
    raw_user_id = (request.headers.get("x-rapidapi-user") or "").strip()

    # RapidAPI provider traffic may not always forward x-rapidapi-key.
    if not any([api_key, proxy_secret, raw_user_id]):
        logger.warning(
            "RapidAPI auth failed path=%s reason=no_identity_headers",
            request.url.path,
        )
        return _unauthorized()

    if _REQUIRE_PROXY_SECRET:
        if not _EXPECTED_PROXY_SECRET:
            logger.error(
                "Proxy secret is required but not configured. "
                "Set RAPIDAPI_PROXY_SECRET or RAPIDAPI_SECRET."
            )
            return JSONResponse(status_code=503, content={"error": "Service unavailable"})

        if not hmac.compare_digest(proxy_secret, _EXPECTED_PROXY_SECRET):
            logger.warning(
                "RapidAPI auth failed path=%s reason=proxy_secret_mismatch",
                request.url.path,
            )
            return _unauthorized()
    elif _EXPECTED_PROXY_SECRET and proxy_secret:
        # If a secret is configured and a header is supplied, it must match.
        if not hmac.compare_digest(proxy_secret, _EXPECTED_PROXY_SECRET):
            logger.warning(
                "RapidAPI auth failed path=%s reason=proxy_secret_mismatch_optional",
                request.url.path,
            )
            return _unauthorized()

    raw_plan = (
        request.headers.get("x-rapidapi-subscription")
        or request.headers.get("x-rapidapi-plan")
        or DEFAULT_PLAN
    ).lower()
    plan = raw_plan if raw_plan in VALID_PLANS else DEFAULT_PLAN

    if _SAFE_ID_RE.match(raw_user_id):
        user_id = raw_user_id
    else:
        identity_seed = api_key or raw_user_id or (request.client.host if request.client else "unknown")
        user_id = f"key-{hashlib.sha256(identity_seed.encode()).hexdigest()[:16]}"

    request.state.user_id = user_id
    request.state.plan = plan

    logger.info("RapidAPI auth OK user=%s plan=%s", user_id, plan)
    return await call_next(request)
