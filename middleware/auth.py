# ============================================================
# middleware/auth.py — RapidAPI Compatible Auth Middleware
# ============================================================

from fastapi import Request
from fastapi.responses import JSONResponse
import hashlib
import re

from config import VALID_PLANS

# Only printable ASCII, 1–128 chars
_SAFE_ID_RE = re.compile(r'^[\x21-\x7E]{1,128}$')


def _anonymous_id(request: Request) -> str:
    client_ip = (request.client.host if request.client else "unknown").encode("utf-8")
    ip_hash = hashlib.sha256(client_ip).hexdigest()[:16]
    return f"anon-{ip_hash}"


async def verify_rapidapi(request: Request, call_next):
    """
    RapidAPI Auth Middleware (Fixed)

    Uses:
    - X-RapidAPI-Key (primary auth)
    - X-RapidAPI-User (optional)
    - X-RapidAPI-Subscription (plan)
    """

    # ✅ Allow health checks
    if request.url.path == "/health":
        return await call_next(request)

    # 🔑 MAIN AUTH (RapidAPI standard)
    api_key = request.headers.get("x-rapidapi-key")

    if not api_key:
        return JSONResponse(
            status_code=401,
            content={"error": "Missing RapidAPI key"}
        )

    # 🧠 Optional headers
    raw_user_id = request.headers.get("x-rapidapi-user", "")
    raw_plan = request.headers.get("x-rapidapi-subscription", "free").lower()

    # ✅ Plan validation
    plan = raw_plan if raw_plan in VALID_PLANS else "free"

    # ✅ User ID sanitization
    if _SAFE_ID_RE.match(raw_user_id):
        user_id = raw_user_id
    else:
        user_id = _anonymous_id(request)

    # Store in request state
    request.state.user_id = user_id
    request.state.plan = plan
    request.state.api_key = api_key  # useful for logging/rate limit

    return await call_next(request)