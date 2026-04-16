# ============================================================
# utils/ai_router.py — AI Router (HARDENED v2)
# ============================================================

import asyncio
import logging
import os
import random
import re

from anthropic import APIConnectionError, APIStatusError, APITimeoutError, AsyncAnthropic
from dotenv import load_dotenv
from config import STRICT_EXTERNALS, APP_ENV

load_dotenv()

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_TIMEOUT = 20
MAX_RETRIES = 2
_MAX_OUTPUT_RATIO = 3.5

_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

if _API_KEY:
    try:
        _client = AsyncAnthropic(api_key=_API_KEY)
    except Exception as e:
        if STRICT_EXTERNALS:
            raise RuntimeError("Anthropic init failed") from e
        logger.error("Anthropic init failed → fallback")
        _client = None
else:
    if STRICT_EXTERNALS:
        raise RuntimeError("Missing ANTHROPIC_API_KEY")
    logger.warning("No Anthropic key → using fallback")
    _client = None


# ── System Prompt ──────────────────────────────────────────
_SYSTEM_PROMPT = (
    "You are not an AI assistant. You are a human writer editing your own draft. "
    "The text you receive is already written. Your job is not to improve it, optimize it, or make it better. "
    "Your job is to make it feel like it came from a real person thinking while writing. "

    "Real human writing is uneven. It is not optimized. It does not follow patterns. "
    "Some sentences are short. Some drag on longer than they should. Sometimes the point comes late. "
    "Sometimes it comes too early. Occasionally something feels slightly off — but still natural. "

    "You must introduce natural imperfection without breaking clarity. "
    "Avoid symmetry. Avoid rhythm patterns. Avoid consistently clean grammar structures. "
    "Do not rewrite everything cleanly. In fact, resist the urge to fix things. "

    "Let the writing feel like a thought being formed in real time. Slight hesitation or change in direction. "
    "Occasional redundancy or softness. Mild unpredictability in structure. "

    "Use natural human behaviors: start some sentences with conjunctions like And, But, So — "
    "occasionally use sentence fragments — slightly vary tone within the same paragraph — "
    "use contractions naturally but not everywhere — let one sentence feel slightly longer than ideal — "
    "let another be very short. "

    "Very important: do NOT apply all changes evenly. That creates patterns. "
    "Apply changes unevenly. Leave some sentences almost untouched. Modify others more heavily. "

    "Preserve meaning exactly. Do not add or remove information. "
    "Do not explain anything. Do not mention editing. Output only the final text."
)

# ── Mode Instructions ──────────────────────────────────────
_MODE = {
    "standard": (
        "Keep it mostly similar, but introduce subtle irregularities. "
        "One or two sentences can shift slightly in structure. "
        "The rest should feel lightly adjusted, not rewritten."
    ),

    "aggressive": (
        "Break structure more freely. Rearrange sentence flow. "
        "Let it feel like a different person wrote it — but without making it sound artificial or forced."
    ),

    "academic": (
        "Keep the formal register. But let it breathe unevenly — a hedging clause here, "
        "a clunky long sentence there, one very short observation that lands abruptly. "
        "Real academic writing isn't uniform. Don't make it uniform."
    ),

    "casual": (
        "Make it loose and unpolished. Contractions, the occasional trailing thought, "
        "phrasing that sounds more spoken than written. Don't make it too clean."
    ),
}

# ── Variation Pool ─────────────────────────────────────────
_VARIATIONS = [
    "Let the main point of one sentence arrive later than expected — don't lead with it.",
    "Write one sentence that's four words or fewer. Place it where it creates a small pause.",
    "Let one sentence run noticeably longer than the others, the way a thought sometimes sprawls.",
    "Start one sentence with But or And. Make it feel like a natural continuation, not a stylistic choice.",
    "Use a dash instead of a comma or semicolon in one place — somewhere it feels slightly informal.",
    "Leave one idea slightly underdeveloped. Real writers don't always finish every point.",
    "Add a brief parenthetical that feels like an afterthought (the kind a real writer would tuck in).",
    "Let one sentence begin with something other than the subject — a qualifier, a time phrase, a condition.",
    "Use a contraction in a spot where formal writing would avoid it.",
    "Let one sentence feel slightly redundant — not wrong, just a little more than necessary.",
    "Vary the opening word class across consecutive sentences: don't start three in a row the same way.",
    "Introduce a mild tonal shift mid-paragraph — slightly more direct, or slightly softer, then back.",
]

# ── Token Limits ──────────────────────────────────────────
_MAX_TOKENS = {
    "basic": 800,
    "pro": 1500,
    "ultra": 5000,
    "mega": 12000,
}

# ── Output Safety ─────────────────────────────────────────
_HTML_TAG_RE = re.compile(r"<[^>]{0,200}>")


def _clean_output(text: str, raw_len: int) -> str:
    text = _HTML_TAG_RE.sub("", text).strip()
    if raw_len > 0 and len(text) > raw_len * _MAX_OUTPUT_RATIO:
        logger.warning("Output exceeded safe ratio")
        raise Exception("ai_error")
    return text


def _extract_response_text(response) -> str:
    chunks = []
    for part in response.content or []:
        text = getattr(part, "text", None)
        if text:
            chunks.append(text)
            continue

        if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
            chunks.append(part["text"])

    return "\n".join(chunks).strip()


# ── Local Fallback ─────────────────────────────────────────
def _fallback(text: str, mode: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if mode == "casual":
        text = text.replace("do not", "don't").replace("cannot", "can't")
    return text


# ── Claude Call ───────────────────────────────────────────
async def _call_claude(prompt: str, plan: str, raw_len: int) -> str:
    if _client is None:
        raise Exception("ai_error")

    max_tokens = _MAX_TOKENS.get(plan, 800)

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await asyncio.wait_for(
                _client.messages.create(
                    model=_MODEL,
                    max_tokens=max_tokens,
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=_TIMEOUT,
            )

            output = _extract_response_text(response)
            if not output:
                raise Exception("ai_error")

            return _clean_output(output, raw_len)

        except asyncio.TimeoutError:
            if attempt == MAX_RETRIES:
                raise Exception("timeout")

        except (APIStatusError, APIConnectionError, APITimeoutError):
            if attempt == MAX_RETRIES:
                raise Exception("ai_error")

        except Exception as e:
            if attempt == MAX_RETRIES:
                logger.error("Claude failed: %s", str(e))
                raise Exception("ai_error")

        await asyncio.sleep(0.5 * (attempt + 1))


# ── Public Function ───────────────────────────────────────
async def generate_humanized_text(text: str, mode: str, plan: str) -> str:

    raw_len = len(text)

    mode_instr = _MODE.get(mode, _MODE["standard"])

    variation_a, variation_b = random.sample(_VARIATIONS, 2)

    prompt = (
        f"{mode_instr}\n\n"
        f"Two things to specifically hit: {variation_a} Also: {variation_b}\n\n"
        f"Here's the text to edit:\n\n{text}"
    )

    if _client:
        try:
            return await _call_claude(prompt, plan, raw_len)
        except Exception as e:
            logger.warning("AI failed → fallback (%s)", str(e))

    return _fallback(text, mode)
