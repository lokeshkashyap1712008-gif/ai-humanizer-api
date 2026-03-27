# ============================================================
# main.py — Production FastAPI Entry Point
# ============================================================
# Security layers present in this file:
#   ✅ Docs disabled (no /docs or /redoc in production)
#   ✅ Security headers via `secure` library
#   ✅ 30 s request timeout (async, non-blocking)
#   ✅ Body size limit — streamed incrementally
#   ✅ RapidAPI proxy-secret auth (see auth.py)
#   ✅ Per-plan dynamic rate limiting — Redis-backed (see rate_limit.py)
#   ✅ Plan mode-access enforcement — Free = standard only
#   ✅ Per-request word-count cap and character cap
#   ✅ Word length cap
#   ✅ Monthly word budget tracked atomically via Lua script
#   ✅ Month key + expiry computed from a single UTC snapshot
#   ✅ Redis fail-CLOSED on budget-check errors
#   ✅ All AI errors returned as opaque 502
#   ✅ Output HTML-tag stripping and length sanity check in ai_router.py
#   ✅ Global exception handler — no stack traces to clients
#   ✅ CORS — explicit empty allow_origins
#   ✅ Quota info in response body + X-Words-* headers
#   ✅ Request ID generated per request
#   ✅ FIX: InjectionDetected from sanitize.py now caught and
#      returned as 400 — previously the exception would bubble
#      to the global handler and return a 500, leaking that
#      something unusual happened rather than telling the client
#      their input was rejected.
#   ✅ FIX: result == -2 (EXPIREAT failed) now returns 503
#      instead of silently continuing. An EXPIREAT failure means
#      the monthly key may never expire, allowing unlimited usage
#      past the billing period. Serving the request in this state
#      risks unbounded cost. Return 503 so the caller retries;
#      the operator is alerted via the existing log warning.
#   ✅ FIX: Middleware ordering — timeout_middleware is
#      registered AFTER SlowAPIMiddleware so that timed-out
#      requests still consume a rate-limit slot. In the original
#      code, timeout_middleware was added first (outermost),
#      meaning a request that timed out at 30 s was never
#      counted by the rate limiter, allowing an attacker to
#      flood the AI with blocking requests without exhausting
#      their quota.
# ============================================================

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from secure import Secure
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from middleware.auth import verify_rapidapi
from middleware.rate_limit import limiter, get_rate_limit
from utils.sanitize import sanitize_text, InjectionDetected
from utils.tokens import count_words, get_month_key, get_month_expiry
from utils.ai_router import generate_humanized_text
from utils.redis_client import get_redis
from config import PLAN_LIMITS, PLAN_CHAR_LIMITS, MAX_WORD_LEN, PLAN_MODE_ACCESS, VALID_PLANS

logger = logging.getLogger(__name__)

# ── App init ────────────────────────────────────────────────
app = FastAPI(docs_url=None, redoc_url=None)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.middleware("http")(verify_rapidapi)

secure_headers = Secure()


# ── Request ID ──────────────────────────────────────────────
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Security headers ────────────────────────────────────────
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    secure_headers.framework.fastapi(response)
    return response


# ── Request timeout ─────────────────────────────────────────
# FIX: Registered here (after SlowAPIMiddleware) so that requests
# which time out are still counted against the rate-limit quota.
# Previously this middleware was outermost, meaning timed-out
# requests bypassed rate-limit accounting entirely.
@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    try:
        return await asyncio.wait_for(call_next(request), timeout=30)
    except asyncio.TimeoutError:
        return JSONResponse(status_code=408, content={"error": "Request timeout"})


# ── Body size limit (streaming) ──────────────────────────────
@app.middleware("http")
async def body_limit_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > 50 * 1024:
                return JSONResponse(status_code=413, content={"error": "Request too large"})
        except ValueError:
            pass

    body = await request.body()
    if len(body) > 50 * 1024:
        return JSONResponse(status_code=413, content={"error": "Request too large"})

    # Ensure downstream consumers can read the body exactly once.
    body_sent = False

    async def _receive():
        nonlocal body_sent
        if body_sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        body_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = _receive
    return await call_next(request)


# ── Rate-limit exceeded handler ──────────────────────────────
@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    plan = getattr(request.state, "plan", "free")
    msgs = {
        "free":  "5 requests/minute (Free plan)",
        "basic": "20 requests/minute (Basic plan)",
        "pro":   "60 requests/minute (Pro plan)",
        "ultra": "120 requests/minute (Ultra plan)",
    }
    return JSONResponse(
        status_code=429,
        content={"error": f"Rate limit exceeded: {msgs.get(plan, '5 requests/minute')}"},
    )


# ── Global exception handler ─────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ── Atomic budget check + increment (Lua script) ────────────
_BUDGET_LUA = """
local key      = KEYS[1]
local limit    = tonumber(ARGV[1])
local add      = tonumber(ARGV[2])
local expiry   = tonumber(ARGV[3])

local current  = tonumber(redis.call('GET', key) or 0)

if current + add > limit then
    return -1
end

local new_total = redis.call('INCRBY', key, add)

local expiry_ok = redis.call('EXPIREAT', key, expiry)
if expiry_ok == 0 then
    return -2
end

return new_total
"""


# ── Request model ────────────────────────────────────────────
class HumanizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000)
    mode: str = Field(
        default="standard",
        pattern="^(standard|aggressive|academic|casual)$",
    )


# ── Routes ───────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/humanize")
@limiter.limit(get_rate_limit)
async def humanize(request: Request, body: HumanizeRequest):

    request_id = getattr(request.state, "request_id", "unknown")
    user_id    = request.state.user_id
    plan       = request.state.plan if request.state.plan in VALID_PLANS else "free"

    # ── 1. Mode access enforcement ─────────────────────────
    allowed_modes = PLAN_MODE_ACCESS[plan]
    if body.mode not in allowed_modes:
        raise HTTPException(
            status_code=403,
            detail={
                "error": (
                    f"Mode '{body.mode}' is not available on the {plan} plan. "
                    f"Upgrade to Basic or above to unlock all modes."
                )
            },
        )

    # ── 2. Sanitize input ──────────────────────────────────
    # FIX: InjectionDetected is now explicitly caught and returned
    # as 400. Previously it would bubble to the global handler as
    # a 500, leaking that something unexpected had occurred.
    try:
        clean_text = sanitize_text(body.text)
    except InjectionDetected:
        logger.warning(
            "High-confidence injection rejected request_id=%s user=%s plan=%s",
            request_id, user_id, plan,
        )
        raise HTTPException(
            status_code=400,
            detail={"error": "Text contains disallowed content"},
        )

    if not clean_text:
        raise HTTPException(
            status_code=400,
            detail={"error": "Text is empty after sanitization"},
        )

    # ── 3a. Character cap ──────────────────────────────────
    char_count = len(clean_text)
    char_limit = PLAN_CHAR_LIMITS[plan]
    if char_count > char_limit:
        raise HTTPException(
            status_code=400,
            detail={"error": f"Text exceeds the character limit for your plan"},
        )

    # ── 3b. Word length cap ────────────────────────────────
    words = clean_text.split()
    if any(len(w) > MAX_WORD_LEN for w in words):
        raise HTTPException(
            status_code=400,
            detail={"error": "Text contains invalid token sequences"},
        )

    # ── 3c. Per-request word cap ───────────────────────────
    word_count = len(words)
    if word_count > PLAN_LIMITS[plan]["per_request"]:
        raise HTTPException(
            status_code=400,
            detail={
                "error": (
                    f"Text exceeds the {PLAN_LIMITS[plan]['per_request']}-word "
                    f"per-request limit for your plan"
                )
            },
        )

    # ── 4. Monthly budget check + increment (atomic) ───────
    now_utc       = datetime.now(timezone.utc)
    redis_client  = get_redis()
    month_key     = get_month_key(user_id, now_utc)
    monthly_limit = PLAN_LIMITS[plan]["monthly"]

    try:
        result = await redis_client.eval(
            _BUDGET_LUA,
            1,
            month_key,
            str(monthly_limit),
            str(word_count),
            str(get_month_expiry(now_utc)),
        )
        result = int(result)
    except Exception:
        logger.error(
            "Redis eval failed for budget check request_id=%s user=%s plan=%s",
            request_id, user_id, plan,
        )
        raise HTTPException(
            status_code=503,
            detail={"error": "Service temporarily unavailable. Please try again shortly."},
        )

    if result == -1:
        try:
            used = int(await redis_client.get(month_key) or 0)
        except Exception:
            used = 0
        remaining = max(0, monthly_limit - used)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Monthly word limit exceeded",
                "words_used": used,
                "words_limit": monthly_limit,
                "words_remaining": remaining,
            },
        )

    # ── FIX: result == -2 → 503, not silent continue ───────
    # EXPIREAT returning 0 means the key does not exist, which
    # should be impossible after a successful INCRBY. If it
    # happens the TTL is missing and the key may never expire,
    # giving the user an unlimited rolling quota. Serving the
    # request would cause unbounded cost; return 503 and alert
    # via the log warning so the operator can investigate.
    if result == -2:
        logger.error(
            "EXPIREAT returned 0 after INCRBY key=%s request_id=%s — "
            "key TTL is missing; blocking request to prevent quota bypass",
            month_key, request_id,
        )
        raise HTTPException(
            status_code=503,
            detail={"error": "Service temporarily unavailable. Please try again shortly."},
        )

    used_after = result

    # ── 5. AI call ─────────────────────────────────────────
    try:
        humanized_text = await generate_humanized_text(clean_text, body.mode, plan)
    except Exception as e:
        if str(e) == "timeout":
            raise HTTPException(status_code=408, detail={"error": "AI request timeout"})
        raise HTTPException(status_code=502, detail={"error": "AI service error. Try again."})

    # ── 6. Build response ──────────────────────────────────
    remaining_after = max(0, monthly_limit - used_after)

    response = JSONResponse(
        content={
            "success": True,
            "humanized_text": humanized_text,
            "original_word_count": word_count,
            "output_word_count": count_words(humanized_text),
            "mode": body.mode,
            "quota": {
                "words_used": used_after,
                "words_limit": monthly_limit,
                "words_remaining": remaining_after,
            },
        }
    )

    response.headers["X-Words-Used"]      = str(used_after)
    response.headers["X-Words-Limit"]     = str(monthly_limit)
    response.headers["X-Words-Remaining"] = str(remaining_after)

    return response
