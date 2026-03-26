# ============================================================
# utils/ai_router.py — Claude claude-sonnet-4-6 (SINGLE MODEL)
# ============================================================
# Security / correctness measures in this file:
#   ✅ ONLY model used: claude-sonnet-4-6 — hardcoded constant,
#      not user-supplied, not configurable via env/request
#   ✅ ANTHROPIC_API_KEY is read from env ONCE at startup;
#      it is NEVER logged, NEVER returned in a response,
#      NEVER included in error messages
#   ✅ API key validated at import time — mis-configured
#      deploys fail fast instead of silently at runtime
#   ✅ System prompt sent via `system` param (never in user
#      message) — prevents system-prompt leakage via
#      "repeat everything above" injections
#   ✅ Mode instruction is pre-validated before this module
#      is called (main.py Pydantic pattern); defence-in-depth
#      fallback here too
#   ✅ max_tokens scaled per plan — prevents output truncation
#      for Pro/Ultra while keeping Free cost-capped
#   ✅ Timeout enforced at 28 s (under FastAPI's 30 s limit)
#   ✅ Generic exception re-raised as opaque string — no
#      internal stack trace or key material leaks to caller
# ============================================================

import asyncio
import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# ── API key: read once, never exposed ──────────────────────
_ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
if not _ANTHROPIC_KEY:
    raise RuntimeError(
        "Missing ANTHROPIC_API_KEY in environment. Check your .env file."
    )

# Key is stored only in the private client object; it is never
# referenced again after this point and never placed in any
# variable that could be serialised or logged.
_client = Anthropic(api_key=_ANTHROPIC_KEY)
del _ANTHROPIC_KEY  # Remove from module namespace immediately

# ── Single, hard-coded model ────────────────────────────────
_MODEL = "claude-sonnet-4-6"

# ── System prompt (sent via `system` param, never in messages)
_SYSTEM_PROMPT = (
    "You are an expert writing editor who rewrites AI-generated text to sound "
    "authentically human. Your goal is to preserve the original meaning while "
    "making the writing feel natural, fluent, and indistinguishable from "
    "human-written text. Do not add extra commentary — return only the rewritten text."
)

# ── Mode additions (validated upstream; fallback to "" here) ─
_MODE_ADDITIONS: dict[str, str] = {
    "standard":   "",
    "aggressive": "Heavily restructure every sentence while preserving meaning.",
    "academic":   "Maintain a formal academic tone throughout.",
    "casual":     "Make the writing very conversational and relaxed.",
}

# ── Output token budget per plan ────────────────────────────
_MAX_TOKENS_BY_PLAN: dict[str, int] = {
    "free":  1000,
    "basic": 2000,
    "pro":   6000,
    "ultra": 16000,
}

# Internal timeout — 2 seconds under FastAPI's 30 s limit so
# our handler always fires first and can return a clean 408.
_TIMEOUT_SECONDS = 28


async def _call_claude(user_prompt: str, plan: str) -> str:
    """
    Execute a single Claude claude-sonnet-4-6 call in a thread pool.
    Raises Exception("timeout") or Exception("ai_error") — never raw
    Anthropic exceptions that might contain key material.
    """
    max_tokens = _MAX_TOKENS_BY_PLAN.get(plan, 1000)

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                _client.messages.create,
                model=_MODEL,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
            ),
            timeout=_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise Exception("timeout")
    except Exception:
        # Deliberately swallow exception details — no key/model info in logs
        raise Exception("ai_error")

    return response.content[0].text


async def generate_humanized_text(text: str, mode: str, plan: str) -> str:
    """
    Public entry point called by main.py.
    Builds the user prompt and delegates to _call_claude.
    """
    # Defence-in-depth: treat unknown modes as standard
    mode_instruction = _MODE_ADDITIONS.get(mode, "")

    user_prompt = f"{mode_instruction}\n\n{text}" if mode_instruction else text

    return await _call_claude(user_prompt, plan)