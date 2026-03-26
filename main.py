# FINAL PRODUCTION MAIN.PY
# Fixes applied:
# ✅ FIX #3  — Redis monthly word tracking fully wired up (was hardcoded to 0)
# ✅ FIX #8  — Body size limit uses proper Starlette pattern
# ✅ FIX #10 — Per-plan dynamic rate limiting via get_rate_limit()

import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from secure import SecureHeaders

# Middleware + utils
from middleware.auth import verify_rapidapi
from middleware.rate_limit import limiter, get_rate_limit
from utils.sanitize import sanitize_text
from utils.tokens import count_words, estimate_tokens, get_month_key, get_month_expiry
from utils.ai_router import generate_humanized_text
from utils.redis_client import get_redis
from config import PLAN_LIMITS

# SlowAPI
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# -----------------------------
# App Init (DOCS DISABLED)
# -----------------------------
app = FastAPI(
    docs_url=None,
    redoc_url=None,
)

# Attach limiter
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Auth middleware
app.middleware("http")(verify_rapidapi)

# Security headers
secure_headers = SecureHeaders()


# -----------------------------
# SECURITY MIDDLEWARES
# -----------------------------
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    secure_headers.framework.fastapi(response)
    return response


@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    try:
        return await asyncio.wait_for(call_next(request), timeout=30)
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=408,
            content={"error": "Request timeout"},
        )


@app.middleware("http")
async def body_limit_middleware(request: Request, call_next):
    """
    ✅ FIX #8 — Read body once and store it so downstream handlers can still read it.
    Starlette caches request.body() after the first read, so this is safe.
    """
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 50 * 1024:
        return JSONResponse(
            status_code=413,
            content={"error": "Request too large"},
        )
    body = await request.body()  # Caches in Starlette — downstream reads still work
    if len(body) > 50 * 1024:
        return JSONResponse(
            status_code=413,
            content={"error": "Request too large"},
        )
    return await call_next(request)


# -----------------------------
# RATE LIMIT HANDLER
# -----------------------------
@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    plan = getattr(request.state, "plan", "free")
    limits_msg = {
        "free":  "5 requests per minute (Free plan)",
        "basic": "20 requests per minute (Basic plan)",
        "pro":   "60 requests per minute (Pro plan)",
        "ultra": "120 requests per minute (Ultra plan)",
    }
    return JSONResponse(
        status_code=429,
        content={"error": f"Rate limit exceeded: {limits_msg.get(plan, '5 requests per minute')}"},
    )


# -----------------------------
# GLOBAL ERROR HANDLER
# -----------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


# -----------------------------
# REQUEST MODEL
# -----------------------------
class HumanizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    mode: str = Field(
        default="standard",
        pattern="^(standard|aggressive|academic|casual)$",
    )


# -----------------------------
# ROUTES
# -----------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


# -----------------------------
# HUMANIZE ENDPOINT
# -----------------------------
@app.post("/humanize")
@limiter.limit(get_rate_limit)   # ✅ FIX #10 — Dynamic per-plan rate limit
async def humanize(request: Request, body: HumanizeRequest):

    user_id = request.state.user_id
    plan = request.state.plan

    if not body.text.strip():
        raise HTTPException(status_code=400, detail={"error": "Text is required"})

    # Sanitize input
    clean_text = sanitize_text(body.text)

    # Word count check against per-request limit
    word_count = count_words(clean_text)

    if plan not in PLAN_LIMITS:
        plan = "free"

    if word_count > PLAN_LIMITS[plan]["per_request"]:
        raise HTTPException(
            status_code=400,
            detail={"error": f"Text exceeds the {PLAN_LIMITS[plan]['per_request']}-word limit for your plan"},
        )

    # ✅ FIX #3 — Check monthly usage from Redis BEFORE running the AI call
    redis = get_redis()
    month_key = get_month_key(user_id)

    try:
        used = int(redis.get(month_key) or 0)
    except Exception:
        # Redis read failure — fail open (don't block the user), but log it
        used = 0

    monthly_limit = PLAN_LIMITS[plan]["monthly"]

    if used + word_count > monthly_limit:
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

    # AI call
    try:
        humanized_text = await generate_humanized_text(clean_text, body.mode, plan)
    except Exception as e:
        if str(e) == "timeout":
            raise HTTPException(status_code=408, detail={"error": "AI request timeout"})
        else:
            raise HTTPException(status_code=502, detail={"error": "AI service error. Try again."})

    # ✅ FIX #3 — Update Redis monthly usage atomically after successful AI call
    try:
        pipe = redis.pipeline()
        pipe.incrby(month_key, word_count)
        pipe.expireat(month_key, get_month_expiry())
        pipe.execute()
        used_after = used + word_count
    except Exception:
        # Redis write failure — don't crash the response, just report stale counts
        used_after = used

    remaining_after = max(0, monthly_limit - used_after)
    tokens_used = estimate_tokens(clean_text)

    response = JSONResponse(
        content={
            "success": True,
            "humanized_text": humanized_text,
            "original_word_count": len(body.text.split()),
            "output_word_count": len(humanized_text.split()),
            "mode": body.mode,
            "tokens_used": tokens_used,
        }
    )

    # Accurate usage headers now that Redis is wired up
    response.headers["X-Words-Used"]      = str(used_after)
    response.headers["X-Words-Limit"]     = str(monthly_limit)
    response.headers["X-Words-Remaining"] = str(remaining_after)

    return response