import random
import re
from typing import List

_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)")

MODE_FACTOR = {
    "standard": 0.6,
    "aggressive": 0.8,
    "academic": 0.5,
    "casual": 0.7,
}

def _p(base, mode):
    return base * MODE_FACTOR.get(mode, 0.7)


def _normalize(text: str) -> str:
    return re.sub(r"\s{2,}", " ", text).strip()


def _split(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_RE.findall(text) if s.strip()]


# ============================
# STRUCTURE ADJUSTMENTS
# ============================

def break_structure(sentence, mode):
    words = sentence.split()

    if len(words) > 14 and random.random() < _p(0.3, mode):
        cut = random.randint(5, len(words) - 5)
        return " ".join(words[:cut]) + ". " + " ".join(words[cut:])

    return sentence


def shorten_sentence(sentence, mode):
    words = sentence.split()

    if len(words) > 10 and random.random() < _p(0.15, mode):
        return " ".join(words[:6]) + "."

    return sentence


# ============================
# MAIN FUNCTION
# ============================

def humanize_post_process(text: str, mode="standard") -> str:
    sentences = _split(text)
    if not sentences:
        return text

    out = []

    for sentence in sentences:

        sentence = break_structure(sentence, mode)
        sentence = shorten_sentence(sentence, mode)

        # slight variation in start
        if random.random() < _p(0.25, mode):
            sentence = sentence[0].lower() + sentence[1:]

        out.append(sentence.strip())

    return _normalize(" ".join(out))