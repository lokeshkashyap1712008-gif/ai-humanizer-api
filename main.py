# Main FastAPI app — FINAL (Auth + AI + Rate Limit + Token Tracking)

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Middleware + utils
from middleware.auth import verify_rapidapi
from middleware.rate_limit import limiter
from utils.sanitize import sanitize_text
from utils.tokens import count_words, estimate_tokens
from utils.ai_router import generate_humanized_text
from config import PLAN_LIMITS

# SlowAPI
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# -----------------------------
# App Init
# -----------------------------
app = FastAPI(
    docs_url="/docs",
    redoc_url="/redoc"
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.middleware("http")(verify_rapidapi)


# -----------------------------
# Rate Limit Handler
# -----------------------------
@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": "Max 10 requests per minute"}
    )


# -----------------------------
# Request Model
# -----------------------------
class HumanizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    mode: str = Field(default="standard", pattern="^(standard|aggressive|academic|casual)$")


# -----------------------------
# Routes
# -----------------------------
@app.get("/")
def root():
    return {"message": "AI Humanizer API running"}


@app.get("/health")
def health():
    return {"status": "ok"}


# -----------------------------
# Humanize Endpoint
# -----------------------------
@app.post("/humanize")
@limiter.limit("10/minute")
async def humanize(request: Request, body: HumanizeRequest):

    user_id = request.state.user_id
    plan = request.state.plan

    if not body.text.strip():
        raise HTTPException(status_code=400, detail={"error": "Text is required"})

    # -----------------------------
    # Sanitize Input
    # -----------------------------
    clean_text = sanitize_text(body.text)

    # -----------------------------
    # Word Count
    # -----------------------------
    word_count = count_words(clean_text)

    if plan not in PLAN_LIMITS:
        plan = "free"

    if word_count > PLAN_LIMITS[plan]["per_request"]:
        raise HTTPException(
            status_code=400,
            detail={"error": "Request exceeds per-request word limit"}
        )

    # -----------------------------
    # AI Generation
    # -----------------------------
    try:
        humanized_text = await generate_humanized_text(
            clean_text,
            body.mode,
            plan
        )
    except Exception as e:
        if str(e) == "timeout":
            raise HTTPException(
                status_code=408,
                detail={"error": "AI request timeout"}
            )
        else:
            raise HTTPException(
                status_code=502,
                detail={"error": "AI service error. Try again."}
            )

    # -----------------------------
    # Token Tracking
    # -----------------------------
    tokens_used = estimate_tokens(clean_text)

    # -----------------------------
    # Usage Headers
    # -----------------------------
    limit = PLAN_LIMITS[plan]["monthly"]
    used = 0  # (Redis later)
    remaining = limit - used

    response = JSONResponse(
        content={
            "success": True,
            "humanized_text": humanized_text,
            "original_word_count": len(body.text.split()),
            "output_word_count": len(humanized_text.split()),
            "mode": body.mode,
            "tokens_used": tokens_used
        }
    )

    response.headers["X-Words-Used"] = str(used)
    response.headers["X-Words-Limit"] = str(limit)
    response.headers["X-Words-Remaining"] = str(remaining)

    return response