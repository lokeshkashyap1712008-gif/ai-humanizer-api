# AI Router — Claude Sonnet 4.6 (Single Model)
# Fixes: wrong model string, mode ignored for Claude, double system prompt,
#        max_tokens too small for higher plans, missing API key validation

import asyncio
import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# ✅ FIX #9 — Validate API key at startup, not silently at runtime
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_KEY:
    raise RuntimeError("Missing ANTHROPIC_API_KEY in environment. Check your .env file.")

anthropic_client = Anthropic(api_key=ANTHROPIC_KEY)

# ✅ FIX #1 — Single correct model string
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are an expert writing editor who rewrites AI-generated text to sound \
authentically human. Your goal is to preserve the original meaning while making the writing \
feel natural, fluent, and indistinguishable from human-written text. Do not add extra \
commentary — return only the rewritten text."""

MODE_ADDITIONS = {
    "standard":   "",
    "aggressive": "Heavily restructure every sentence while preserving meaning.",
    "academic":   "Maintain a formal academic tone throughout.",
    "casual":     "Make the writing very conversational and relaxed.",
}

# ✅ FIX #11 — Scale max_tokens per plan so Pro/Ultra output is never truncated
MAX_TOKENS_BY_PLAN = {
    "free":  1000,
    "basic": 2000,
    "pro":   6000,
    "ultra": 16000,
}


async def call_claude(user_prompt: str, plan: str) -> str:
    """
    Call Claude Sonnet 4.6.
    - system param holds the base system prompt (with prompt caching enabled)
    - user_prompt contains only the mode instruction + user text
    ✅ FIX #4 — System prompt is sent ONCE via the system param, not prepended to user message
    """
    max_tokens = MAX_TOKENS_BY_PLAN.get(plan, 1000)

    response = await asyncio.to_thread(
        anthropic_client.messages.create,
        model=MODEL,
        max_tokens=max_tokens,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},  # Saves ~90% cost on repeated system prompt
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


async def generate_humanized_text(text: str, mode: str, plan: str) -> str:
    """
    Build the user-facing prompt and route to Claude.
    ✅ FIX #2 — Mode instruction is correctly included in the prompt passed to Claude
    """
    mode_instruction = MODE_ADDITIONS.get(mode, "")

    # Build user prompt: mode instruction (if any) + the text to humanize
    if mode_instruction:
        user_prompt = f"{mode_instruction}\n\n{text}"
    else:
        user_prompt = text

    try:
        return await asyncio.wait_for(call_claude(user_prompt, plan), timeout=30)
    except asyncio.TimeoutError:
        raise Exception("timeout")
    except Exception:
        raise Exception("ai_error")