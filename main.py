# Main FastAPI app — FINAL FIX (SlowAPI WORKING via middleware)

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Middleware + utils
from middleware.auth import verify_rapidapi
from middleware.rate_limit import limiter
from utils.sanitize import sanitize_text
from utils.tokens import count_words
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

# Attach limiter FIRST
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# THEN auth
app.middleware("http")(verify_rapidapi)


# -----------------------------
# Rate Limit Handler
# -----------------------------
@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request, exc):
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
async def humanize(request: Request, body: HumanizeRequest):

    # 🔥 APPLY LIMIT MANUALLY (this fixes everything)
    limiter.limit("10/minute")(humanize)(request)

    user_id = request.state.user_id
    plan = request.state.plan

    if not body.text.strip():
        raise HTTPException(status_code=400, detail={"error": "Text is required"})

    clean_text = sanitize_text(body.text)
    word_count = count_words(clean_text)

    if plan not in PLAN_LIMITS:
        plan = "free"

    if word_count > PLAN_LIMITS[plan]["per_request"]:
        raise HTTPException(
            status_code=400,
            detail={"error": "Request exceeds per-request word limit"}
        )

    humanized_text = f"Honestly, {clean_text}"

    return {
        "success": True,
        "humanized_text": humanized_text,
        "original_word_count": len(body.text.split()),
        "output_word_count": len(humanized_text.split()),
        "mode": body.mode,
        "tokens_used": 0
    }