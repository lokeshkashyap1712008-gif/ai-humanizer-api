import asyncio
import logging
import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv
from anthropic import AsyncAnthropic
from utils.quality_gate import score_candidate

load_dotenv()
logger = logging.getLogger(__name__)

_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

_client = AsyncAnthropic(api_key=_API_KEY) if _API_KEY else None


@dataclass
class GenerationResult:
    text: str
    provider_used: str
    model: str
    fallback_used: bool


# ============================
# HELPERS
# ============================

def _get_candidate_count(plan: str) -> int:
    return {
        "basic": 1,
        "pro": 2,
        "ultra": 3,
        "mega": 3,
    }.get(plan, 2)


# ============================
# SPLIT CHUNKS
# ============================

def _split_chunks(text: str, size: int = 3):
    sentences = re.split(r'(?<=[.!?]) +', text)
    return [" ".join(sentences[i:i+size]).strip()
            for i in range(0, len(sentences), size)]

# ============================
# AI CALL
# ============================

async def _call_claude(prompt: str):
    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=1200,
        temperature=0.85,
        system=(
            "Rewrite naturally with strong clarity while preserving meaning. "
            "Do not invent facts, remove key details, or add fluff."
        ),
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ============================
# MULTI CANDIDATE ENGINE
# ============================

async def _single_candidate_rewrite(text: str, mode: str, style_hint: str) -> str:
    chunks = _split_chunks(text, 3)
    rewritten = []

    for ch in chunks:
        rewritten.append(
            await _call_claude(
                f"""
Rewrite this chunk with a different sentence structure.
Mode: {mode}
Style hint: {style_hint}

Rules:
- keep all original meaning
- keep topic and intent unchanged
- improve fluency and readability
- keep output concise and coherent

Chunk:
{ch}
"""
            )
        )

    combined = " ".join(rewritten)

    return await _call_claude(
        f"""
Do a final editorial pass on this rewritten text.
Mode: {mode}
Style hint: {style_hint}

Rules:
- preserve meaning exactly
- improve transitions and flow
- vary sentence lengths naturally
- avoid repetitive phrasing
- keep all key points from source

Text to polish:
{combined}
"""
    )

async def _generate_best_candidate(text: str, mode: str, plan: str) -> str:
    candidate_count = _get_candidate_count(plan)
    style_hints = [
        "direct and structured",
        "slightly conversational but professional",
        "clear explanatory with concrete phrasing",
    ]
    selected_hints = style_hints[:candidate_count]

    candidates = await asyncio.gather(
        *[
            _single_candidate_rewrite(text=text, mode=mode, style_hint=hint)
            for hint in selected_hints
        ]
    )

    best_text = candidates[0]
    best_score = score_candidate(text, best_text)

    for candidate in candidates[1:]:
        candidate_score = score_candidate(text, candidate)
        if candidate_score.total > best_score.total:
            best_text = candidate
            best_score = candidate_score

    # One rescue attempt if all candidates fail the gate.
    if not best_score.passed and candidate_count > 1:
        rescue = await _single_candidate_rewrite(
            text=text,
            mode=mode,
            style_hint="high-fidelity rewrite focused on retaining every key idea",
        )
        rescue_score = score_candidate(text, rescue)
        if rescue_score.total > best_score.total:
            best_text = rescue
            best_score = rescue_score

    logger.info(
        "quality_gate score=%.4f passed=%s meaning=%.4f diversity=%.4f",
        best_score.total,
        best_score.passed,
        best_score.meaning_overlap,
        best_score.diversity,
    )
    return best_text


# ============================
# MAIN FUNCTION
# ============================

async def generate_humanized_text(text: str, mode: str, plan: str) -> GenerationResult:

    from utils.post_process import humanize_post_process

    if _client:
        try:
            result = await _generate_best_candidate(text=text, mode=mode, plan=plan)
            result = humanize_post_process(result, mode)

            return GenerationResult(result, "anthropic", _MODEL, False)

        except Exception:
            fallback = humanize_post_process(text, mode)
            return GenerationResult(fallback, "fallback", _MODEL, True)

    fallback = humanize_post_process(text, mode)
    return GenerationResult(fallback, "fallback", _MODEL, True)