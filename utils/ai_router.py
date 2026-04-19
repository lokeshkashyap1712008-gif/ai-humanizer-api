import asyncio
import logging
import os
import random
import re
from dataclasses import dataclass

from dotenv import load_dotenv
from anthropic import AsyncAnthropic

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
# HARD TEXT DETECTION
# ============================

def _is_hard_text(text: str) -> bool:
    words = text.split()
    if len(words) > 120:
        return True

    if any(k in text.lower() for k in [
        "history", "war", "biological", "process",
        "system", "development", "analysis"
    ]):
        return True

    return False


# ============================
# SPLIT CHUNKS
# ============================

def _split_chunks(text: str, size: int = 3):
    sentences = re.split(r'(?<=[.!?]) +', text)
    return [" ".join(sentences[i:i+size]).strip()
            for i in range(0, len(sentences), size)]


# ============================
# SENTENCE / PARAGRAPH HELPERS
# ============================

def _split_sentences(text: str):
    return [s.strip() for s in re.split(r'(?<=[.!?]) +', text) if s.strip()]


def _make_paragraphs(text: str):
    sents = _split_sentences(text)
    if len(sents) < 6:
        return text

    paras, i = [], 0
    while i < len(sents):
        size = random.choice([2, 3])
        paras.append(" ".join(sents[i:i+size]))
        i += size

    return "\n\n".join(paras)


def _light_reorder_paragraphs(text: str):
    paras = [p for p in text.split("\n\n") if p.strip()]
    if len(paras) > 2 and random.random() < 0.5:
        i = random.randint(0, len(paras)-2)
        paras[i], paras[i+1] = paras[i+1], paras[i]
    return "\n\n".join(paras)


def _pick_voice():
    return random.choice([
        "explain with a small example first",
        "slightly reflective tone",
        "contrast style (idea then limitation)",
        "simple explanatory tone"
    ])


# ============================
# AI CALL
# ============================

async def _call_claude(prompt: str):
    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=1200,
        temperature=0.85,
        system=(
            "Rewrite like a human. "
            "Do not keep original structure. "
            "Keep meaning same."
        ),
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ============================
# MULTI PASS ENGINE
# ============================

async def _multi_pass_rewrite(text: str):

    is_hard = _is_hard_text(text)

    # PASS 1 — chunk rewrite
    chunks = _split_chunks(text, 3)
    rewritten = []

    for ch in chunks:
        rewritten.append(await _call_claude(
            f"Rewrite with different structure:\n{ch}"
        ))

    combined = " ".join(rewritten)

    # PASS 2 — humanization
    step2 = await _call_claude(
        f"""
Rewrite again:

- vary sentence length
- avoid uniform flow
- slightly imperfect tone

Text:
{combined}
"""
    )

    # paragraph restructuring
    step2 = _make_paragraphs(step2)
    step2 = _light_reorder_paragraphs(step2)

    # 🔥 FINAL PASS ONLY FOR HARD TEXT
    if is_hard:
        voice = _pick_voice()
        step3 = await _call_claude(
            f"""
Rewrite this with a {voice}.

- you may slightly change order
- keep meaning exact
- avoid smooth AI flow

Text:
{step2}
"""
        )
        return step3

    return step2


# ============================
# MAIN FUNCTION
# ============================

async def generate_humanized_text(text: str, mode: str, plan: str) -> GenerationResult:

    from utils.post_process import humanize_post_process

    if _client:
        try:
            result = await _multi_pass_rewrite(text)
            result = humanize_post_process(result, mode)

            return GenerationResult(result, "anthropic", _MODEL, False)

        except Exception:
            fallback = humanize_post_process(text, mode)
            return GenerationResult(fallback, "fallback", _MODEL, True)

    fallback = humanize_post_process(text, mode)
    return GenerationResult(fallback, "fallback", _MODEL, True)