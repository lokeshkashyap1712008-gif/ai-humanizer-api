import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from secure import Secure
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from middleware.auth import verify_rapidapi

from middleware.rate_limit import limiter, get_rate_limit
from utils.sanitize import sanitize_text, InjectionDetected
from utils.post_process import humanize_post_process
from utils.tokens import count_words, get_month_key, get_month_expiry
from utils.ai_router import generate_humanized_text
from utils.redis_client import get_redis
from config import (
    DEFAULT_PLAN,
    PLAN_CONFIG,
    PLAN_LIMITS,
    PLAN_CHAR_LIMITS,
    MAX_WORD_LEN,
    PLAN_MODE_ACCESS,
    RATE_LIMITS,
    VALID_PLANS,
)

# ── Config ────────────────────────────────────────────────
MAX_BODY_SIZE = int(os.getenv("MAX_BODY_SIZE", 50 * 1024))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 30))
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── App Init ──────────────────────────────────────────────
app = FastAPI(docs_url=None, redoc_url=None)


AUTH_DEBUG_VERSION = "rapidapi-auth-debug-v2"
logger.info("Starting app with %s", AUTH_DEBUG_VERSION)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

secure_headers = Secure()

# ── Auth Middleware ───────────────────────────────────────
app.middleware("http")(verify_rapidapi)


# ── Request ID Middleware ─────────────────────────────────
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Security Headers ──────────────────────────────────────
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)

    # ✅ FIXED: correct method
    secure_headers.framework.fastapi(response)

    return response


# ── Timeout Middleware ────────────────────────────────────
@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    try:
        return await asyncio.wait_for(call_next(request), timeout=REQUEST_TIMEOUT)
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=408,
            content={"error": "Request timeout"},
        )


# ── Body Size Limit (Streaming Safe) ──────────────────────
@app.middleware("http")
async def body_limit_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"error": "Request too large"},
                )
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid Content-Length header"},
            )
    else:
        body = await request.body()
        if len(body) > MAX_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"error": "Request too large"},
            )

    return await call_next(request)


# ── Rate Limit Handler ────────────────────────────────────
@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    plan = getattr(request.state, "plan", DEFAULT_PLAN)
    msgs = {
        name: limit.replace("/minute", " requests/minute")
        for name, limit in RATE_LIMITS.items()
    }

    return JSONResponse(
        status_code=429,
        content={
            "error": (
                f"Rate limit exceeded: "
                f"{msgs.get(plan, msgs[DEFAULT_PLAN])}"
            )
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "Validation error path=%s errors=%s",
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={"error": "Invalid request body", "details": exc.errors()},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": detail},
    )


# ── Global Exception Handler ──────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled error request_id=%s",
        getattr(request.state, "request_id", "unknown"),
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


# ── Lua Scripts (Quota System) ─────────────────────────────
# Words quota tracking
_WORDS_BUDGET_LUA = """
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

# Requests quota tracking
_REQUESTS_BUDGET_LUA = """
local key      = KEYS[1]
local limit    = tonumber(ARGV[1])
local expiry   = tonumber(ARGV[2])

local current  = tonumber(redis.call('GET', key) or 0)

if current + 1 > limit then
    return -1
end

local new_total = redis.call('INCR', key)

local expiry_ok = redis.call('EXPIREAT', key, expiry)
if expiry_ok == 0 then
    return -2
end

return new_total
"""


# ── Request Model ─────────────────────────────────────────
class HumanizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_BODY_SIZE)
    mode: str = Field(
        default="standard",
        pattern="^(standard|aggressive|academic|casual)$",
    )


# ── Root Route ────────────────────────────────────────────
@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"status": "ok", "service": "ai-humanizer-api"}


# ── Health Route ──────────────────────────────────────────
@app.get("/health")
async def health():
    try:
        redis = get_redis()
        await redis.ping()
        return {"status": "ok"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded"},
        )


# ── v1 API Routes ─────────────────────────────────────────
# All core endpoints are prefixed with /v1 for version management

@app.post("/v1/humanize")
@app.post("/humanize")
@limiter.limit(get_rate_limit)
async def humanize(
    request: Request,
    body: HumanizeRequest,
):
    if not hasattr(request.state, "user_id"):
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not hasattr(request.state, "plan") or request.state.plan not in VALID_PLANS:
        raise HTTPException(status_code=401, detail="Invalid subscription plan")

    user_id = request.state.user_id
    plan = request.state.plan
    request_id = getattr(request.state, "request_id", "unknown")

    # Mode access
    if body.mode not in PLAN_MODE_ACCESS[plan]:
        raise HTTPException(status_code=403, detail="Mode not allowed for your plan")

    # Sanitize
    try:
        clean_text = sanitize_text(body.text)
    except InjectionDetected:
        logger.warning("Injection detected request_id=%s", request_id)
        raise HTTPException(status_code=400, detail="Invalid input")

    if not clean_text:
        raise HTTPException(status_code=400, detail="Empty text")

    # Limits
    if len(clean_text) > PLAN_CHAR_LIMITS[plan]:
        raise HTTPException(status_code=400, detail="Character limit exceeded")

    words = clean_text.split()

    if any(len(w) > MAX_WORD_LEN for w in words):
        raise HTTPException(status_code=400, detail="Invalid token detected")

    if len(words) > PLAN_LIMITS[plan]["per_request"]:
        raise HTTPException(status_code=400, detail="Word limit exceeded")

    word_count = count_words(clean_text)

    # Redis quota tracking
    now = datetime.now(timezone.utc)
    redis = get_redis()
    month_expiry = get_month_expiry(now)

    # Track words quota
    words_key = get_month_key(user_id, now)
    try:
        words_result = await redis.eval(
            _WORDS_BUDGET_LUA,
            1,
            words_key,
            str(PLAN_LIMITS[plan]["monthly_words"]),
            str(word_count),
            str(month_expiry),
        )
        words_result = int(words_result)
    except Exception:
        raise HTTPException(status_code=503, detail="Service unavailable")

    if words_result == -1:
        raise HTTPException(status_code=429, detail="Monthly word limit exceeded")

    if words_result == -2:
        raise HTTPException(status_code=503, detail="Quota system error")

    # Track request quota
    requests_key = f"req:{user_id}:{now.year}-{now.month:02d}"
    try:
        requests_result = await redis.eval(
            _REQUESTS_BUDGET_LUA,
            1,
            requests_key,
            str(PLAN_LIMITS[plan]["monthly_requests"]),
            str(month_expiry),
        )
        requests_result = int(requests_result)
    except Exception:
        # Don't fail the request if request tracking fails, but log it
        logger.error("Request quota tracking failed request_id=%s", request_id)
        requests_result = 0

    if requests_result == -1:
        raise HTTPException(status_code=429, detail="Monthly request limit exceeded")
    if requests_result == -2:
        raise HTTPException(status_code=503, detail="Quota system error")

    # AI call
    try:
        generation = await asyncio.wait_for(
            generate_humanized_text(clean_text, body.mode, plan),
            timeout=15,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="AI timeout")
    except Exception:
        raise HTTPException(status_code=502, detail="AI error")

    if generation.fallback_used:
        post_processed = generation.text
    else:
        post_processed = humanize_post_process(generation.text, body.mode)
    monthly_word_limit = PLAN_LIMITS[plan]["monthly_words"]
    monthly_request_limit = PLAN_LIMITS[plan]["monthly_requests"]
    words_remaining = max(monthly_word_limit - words_result, 0)
    requests_remaining = max(monthly_request_limit - requests_result, 0)

    # Build response with RapidAPI compliant headers
    response_data = {
        "success": True,
        "humanized_text": post_processed,
        "original_word_count": word_count,
        "output_word_count": count_words(post_processed),
        "mode": body.mode,
        "generation": {
            "provider_used": generation.provider_used,
            "model": generation.model,
            "fallback_used": generation.fallback_used,
        },
        "quota": {
            "words_used": words_result,
            "words_limit": monthly_word_limit,
            "words_remaining": words_remaining,
            "requests_used": requests_result,
            "requests_limit": monthly_request_limit,
            "requests_remaining": requests_remaining,
        },
    }

    # Add RapidAPI-style rate limit headers
    headers = {
        "X-Ratelimit-Limit": str(monthly_request_limit),
        "X-Ratelimit-Remaining": str(requests_remaining),
        "X-Ratelimit-Reset": str(month_expiry),
    }

    return JSONResponse(content=response_data, headers=headers)


# ── Usage Endpoint ─────────────────────────────────────────
@app.get("/v1/usage")
@app.get("/usage")  # Legacy support
@limiter.limit(get_rate_limit)
async def get_usage(
    request: Request,
):
    """Get current usage statistics for the authenticated RapidAPI user."""
    if not hasattr(request.state, "user_id"):
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not hasattr(request.state, "plan") or request.state.plan not in VALID_PLANS:
        raise HTTPException(status_code=401, detail="Invalid subscription plan")

    user_id = request.state.user_id
    plan = request.state.plan

    now = datetime.now(timezone.utc)
    redis = get_redis()
    month_expiry = get_month_expiry(now)

    # Get current usage from Redis
    words_key = get_month_key(user_id, now)
    requests_key = f"req:{user_id}:{now.year}-{now.month:02d}"

    try:
        words_used = int(await redis.get(words_key) or 0)
        requests_used = int(await redis.get(requests_key) or 0)
    except Exception:
        raise HTTPException(status_code=503, detail="Service unavailable")

    plan_limits = PLAN_LIMITS[plan]
    words_remaining = max(plan_limits["monthly_words"] - words_used, 0)
    requests_remaining = max(plan_limits["monthly_requests"] - requests_used, 0)

    response_data = {
        "plan": plan,
        "period": f"{now.year}-{now.month:02d}",
        "quotas": {
            "words": {
                "used": words_used,
                "limit": plan_limits["monthly_words"],
                "remaining": words_remaining,
            },
            "requests": {
                "used": requests_used,
                "limit": plan_limits["monthly_requests"],
                "remaining": requests_remaining,
            },
        },
        "limits": {
            "per_request_words": plan_limits["per_request"],
            "available_modes": list(PLAN_MODE_ACCESS[plan]),
        },
    }

    headers = {
        "X-Ratelimit-Limit": str(plan_limits["monthly_requests"]),
        "X-Ratelimit-Remaining": str(requests_remaining),
        "X-Ratelimit-Reset": str(month_expiry),
    }

    return JSONResponse(content=response_data, headers=headers)


# ── Plan Info Endpoint ────────────────────────────────────
@app.get("/v1/plan")
@app.get("/plan")  # Legacy support
async def get_plan_info():
    """Get information about all available plans."""
    return {
        "plans": {
            plan: {
                "price": cfg["price"],
                "monthly_words": cfg["monthly_words"],
                "monthly_requests": cfg["monthly_requests"],
                "per_request_words": cfg["per_request_words"],
                "modes": list(cfg["modes"]),
                "priority": cfg["priority"],
                "bulk": cfg["bulk"],
            }
            for plan, cfg in PLAN_CONFIG.items()
        }
    }
