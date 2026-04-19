# ============================================================
# utils/ai_router.py - AI Router (HARDENED v3)
# ============================================================

import asyncio
import logging
import os
import random
import re
from dataclasses import dataclass

from dotenv import load_dotenv

from config import STRICT_EXTERNALS

try:
    from anthropic import APIConnectionError, APIStatusError, APITimeoutError, AsyncAnthropic
    _ANTHROPIC_SDK_AVAILABLE = True
    _ANTHROPIC_IMPORT_ERROR = ""
except Exception as exc:
    APIConnectionError = APIStatusError = APITimeoutError = Exception
    AsyncAnthropic = None  # type: ignore[assignment]
    _ANTHROPIC_SDK_AVAILABLE = False
    _ANTHROPIC_IMPORT_ERROR = str(exc)

load_dotenv()

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-20250514"
_MODEL = (os.getenv("ANTHROPIC_MODEL") or _DEFAULT_MODEL).strip()
_TIMEOUT = 20
MAX_RETRIES = 2
_MAX_OUTPUT_RATIO = 3.5
_ALLOW_LOCAL_FALLBACK = os.getenv("ALLOW_LOCAL_FALLBACK", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

if _API_KEY and _ANTHROPIC_SDK_AVAILABLE:
    try:
        _client = AsyncAnthropic(api_key=_API_KEY)
    except Exception as exc:
        if STRICT_EXTERNALS:
            raise RuntimeError("Anthropic init failed") from exc
        logger.error("Anthropic init failed, fallback may be used")
        _client = None
elif _API_KEY and not _ANTHROPIC_SDK_AVAILABLE:
    if STRICT_EXTERNALS:
        raise RuntimeError("Anthropic SDK is unavailable")
    logger.error("Anthropic SDK import failed, fallback mode is active: %s", _ANTHROPIC_IMPORT_ERROR)
    _client = None
else:
    if STRICT_EXTERNALS:
        raise RuntimeError("Missing ANTHROPIC_API_KEY")
    logger.warning("No Anthropic key, fallback mode is active")
    _client = None


@dataclass
class GenerationResult:
    text: str
    provider_used: str
    model: str
    fallback_used: bool
    fallback_reason: str = ""


_SYSTEM_PROMPT = (
    "You are not an AI assistant. You are a human writer editing your own draft. "
    "The text you receive is already written. Your job is not to improve it, optimize it, or make it better. "
    "Your job is to make it feel like it came from a real person thinking while writing. "
    "Real human writing is uneven. It is not optimized. It does not follow patterns. "
    "Some sentences are short. Some drag on longer than they should. Sometimes the point comes late. "
    "Sometimes it comes too early. Occasionally something feels slightly off, but still natural. "
    "You must introduce natural imperfection without breaking clarity. "
    "Avoid symmetry. Avoid rhythm patterns. Avoid consistently clean grammar structures. "
    "Do not rewrite everything cleanly. In fact, resist the urge to fix things. "
    "Let the writing feel like a thought being formed in real time. Slight hesitation or change in direction. "
    "Occasional redundancy or softness. Mild unpredictability in structure. "
    "Use natural human behaviors: start some sentences with conjunctions like And, But, So; "
    "occasionally use sentence fragments; slightly vary tone within the same paragraph; "
    "use contractions naturally but not everywhere; let one sentence feel slightly longer than ideal; "
    "let another be very short. "
    "Very important: do NOT apply all changes evenly. That creates patterns. "
    "Apply changes unevenly. Leave some sentences almost untouched. Modify others more heavily. "
    "Preserve meaning exactly. Do not add or remove information. "
    "Do not explain anything. Do not mention editing. Output only the final text."
)

_MODE = {
    "standard": (
        "Keep it mostly similar, but introduce subtle irregularities. "
        "One or two sentences can shift slightly in structure. "
        "The rest should feel lightly adjusted, not rewritten."
    ),
    "aggressive": (
        "Break structure more freely. Rearrange sentence flow. "
        "Let it feel like a different person wrote it, but without making it sound artificial or forced."
    ),
    "academic": (
        "Keep the formal register. But let it breathe unevenly: a hedging clause here, "
        "a clunky long sentence there, one very short observation that lands abruptly. "
        "Real academic writing is not uniform. Do not make it uniform."
    ),
    "casual": (
        "Make it loose and unpolished. Contractions, the occasional trailing thought, "
        "phrasing that sounds more spoken than written. Do not make it too clean."
    ),
}

_VARIATIONS = [
    "Let the main point of one sentence arrive later than expected, do not lead with it.",
    "Write one sentence that is four words or fewer and place it where it creates a small pause.",
    "Let one sentence run noticeably longer than the others, the way a thought sometimes sprawls.",
    "Start one sentence with But or And, and make it feel like a natural continuation.",
    "Use a dash instead of a comma or semicolon in one place where it feels slightly informal.",
    "Leave one idea slightly underdeveloped.",
    "Add a brief parenthetical that feels like an afterthought.",
    "Let one sentence begin with a qualifier, time phrase, or condition instead of the subject.",
    "Use a contraction in a spot where formal writing would usually avoid it.",
    "Let one sentence feel slightly redundant, not wrong, just a little more than necessary.",
    "Vary opening word class across consecutive sentences.",
    "Introduce a mild tonal shift mid-paragraph, then return.",
]

_MAX_TOKENS = {
    "basic": 800,
    "pro": 1500,
    "ultra": 5000,
    "mega": 12000,
}

_HTML_TAG_RE = re.compile(r"<[^>]{0,200}>")


class AIUnavailableError(RuntimeError):
    pass


def _clean_output(text: str, raw_len: int) -> str:
    clean = _HTML_TAG_RE.sub("", text).strip()
    if raw_len > 0 and len(clean) > raw_len * _MAX_OUTPUT_RATIO:
        logger.warning("AI output exceeded safe ratio")
        raise AIUnavailableError("ai_output_ratio_exceeded")
    return clean


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


def _fallback(text: str, mode: str) -> str:
    from utils.post_process import humanize_post_process

    base = re.sub(r"\s+", " ", text).strip()
    if mode == "casual":
        base = (
            base.replace("do not", "don't")
            .replace("cannot", "can't")
            .replace("will not", "won't")
        )
    return humanize_post_process(base, mode)


async def _call_claude(prompt: str, plan: str, raw_len: int) -> str:
    if _client is None:
        raise AIUnavailableError("client_not_initialized")

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
                raise AIUnavailableError("empty_response")

            return _clean_output(output, raw_len)
        except asyncio.TimeoutError as exc:
            if attempt == MAX_RETRIES:
                raise AIUnavailableError("timeout") from exc
        except (APIStatusError, APIConnectionError, APITimeoutError) as exc:
            if attempt == MAX_RETRIES:
                raise AIUnavailableError("provider_error") from exc
        except AIUnavailableError:
            raise
        except Exception as exc:
            if attempt == MAX_RETRIES:
                logger.error("Anthropic call failed: %s", str(exc))
                raise AIUnavailableError("unknown_error") from exc

        await asyncio.sleep(0.5 * (attempt + 1))

    raise AIUnavailableError("retry_exhausted")


async def generate_humanized_text(text: str, mode: str, plan: str) -> GenerationResult:
    raw_len = len(text)
    mode_instr = _MODE.get(mode, _MODE["standard"])
    variation_a, variation_b = random.sample(_VARIATIONS, 2)

    prompt = (
        f"{mode_instr}\n\n"
        f"Two things to specifically hit: {variation_a} Also: {variation_b}\n\n"
        f"Here is the text to edit:\n\n{text}"
    )

    if _client:
        try:
            ai_text = await _call_claude(prompt, plan, raw_len)
            return GenerationResult(
                text=ai_text,
                provider_used="anthropic",
                model=_MODEL,
                fallback_used=False,
            )
        except AIUnavailableError as exc:
            reason = str(exc) or "ai_failed"
            logger.warning("AI failed, reason=%s", reason)
            if not _ALLOW_LOCAL_FALLBACK:
                raise
            fallback_text = _fallback(text, mode)
            return GenerationResult(
                text=fallback_text,
                provider_used="local_fallback",
                model=_MODEL,
                fallback_used=True,
                fallback_reason=reason,
            )

    if not _ALLOW_LOCAL_FALLBACK:
        raise AIUnavailableError("anthropic_not_configured")

    fallback_text = _fallback(text, mode)
    return GenerationResult(
        text=fallback_text,
        provider_used="local_fallback",
        model=_MODEL,
        fallback_used=True,
        fallback_reason="anthropic_not_configured",
    )
