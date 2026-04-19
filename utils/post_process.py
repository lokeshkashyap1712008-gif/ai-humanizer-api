import random
import re
from typing import List, Tuple

_CONTRACTIONS = {
    "do not": "don't",
    "does not": "doesn't",
    "did not": "didn't",
    "cannot": "can't",
    "will not": "won't",
    "it is": "it's",
    "that is": "that's",
    "there is": "there's",
    "I am": "I'm",
    "we are": "we're",
    "you are": "you're",
    "they are": "they're",
}

_FILLERS = ["kind of", "maybe", "honestly", "to be fair", "in a way"]
_CONNECTORS = ["And", "But", "So"]

_INTENSITY = {
    "standard": 0.22,
    "academic": 0.14,
    "casual": 0.38,
    "aggressive": 0.52,
}

_MIN_CHANGES = {
    "standard": 1,
    "academic": 1,
    "casual": 2,
    "aggressive": 2,
}

_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)")


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s{2,}", " ", text).strip()


def _split_sentences(text: str) -> List[str]:
    return [segment.strip() for segment in _SENTENCE_RE.findall(text) if segment and segment.strip()]


def _swap_contraction(sentence: str) -> Tuple[str, bool]:
    for src, dst in _CONTRACTIONS.items():
        updated = re.sub(rf"\b{re.escape(src)}\b", dst, sentence, count=1, flags=re.IGNORECASE)
        if updated != sentence:
            return updated, True
    return sentence, False


def _insert_connector(sentence: str) -> Tuple[str, bool]:
    stripped = sentence.lstrip()
    if not stripped:
        return sentence, False
    if re.match(r"^(and|but|so)\b", stripped, flags=re.IGNORECASE):
        return sentence, False
    return f"{random.choice(_CONNECTORS)} {stripped}", True


def _insert_filler(sentence: str) -> Tuple[str, bool]:
    filler = random.choice(_FILLERS)
    base = sentence.rstrip()
    if not base:
        return sentence, False

    if base.endswith((".", "!", "?")):
        return f"{base[:-1]}, {filler}{base[-1]}", True

    return f"{base}, {filler}", True


def _split_long_sentence(sentence: str) -> Tuple[str, bool]:
    if len(sentence) < 110:
        return sentence, False

    pivot = len(sentence) // 2
    left_space = sentence.rfind(" ", 0, pivot)
    right_space = sentence.find(" ", pivot)
    split_at = left_space if left_space != -1 else right_space
    if split_at == -1:
        return sentence, False

    left = sentence[:split_at].strip()
    right = sentence[split_at:].strip()
    if not left or not right:
        return sentence, False

    if left[-1] not in ".!?":
        left = f"{left}."

    return f"{left} {right}", True


def _merge_with_next(sentence: str, next_sentence: str) -> Tuple[str, bool]:
    base = sentence.rstrip()
    nxt = next_sentence.strip()

    if not base or not nxt:
        return sentence, False

    if base.endswith((".", "!", "?")):
        base = base[:-1]

    if len(nxt) > 1:
        nxt = f"{nxt[0].lower()}{nxt[1:]}"
    else:
        nxt = nxt.lower()

    return f"{base} {nxt}", True


def humanize_post_process(text: str, mode: str = "standard") -> str:
    if not text or not text.strip():
        return ""

    clean_text = _normalize_ws(text)
    sentences = _split_sentences(clean_text)
    if not sentences:
        return clean_text

    intensity = _INTENSITY.get(mode, _INTENSITY["standard"])
    min_changes = _MIN_CHANGES.get(mode, 1)

    processed: List[str] = []
    i = 0
    changes = 0

    while i < len(sentences):
        sentence = sentences[i]

        if random.random() < intensity:
            sentence, changed = _swap_contraction(sentence)
            changes += int(changed)

        if random.random() < intensity * 0.7:
            sentence, changed = _split_long_sentence(sentence)
            changes += int(changed)

        if random.random() < intensity * 0.55:
            sentence, changed = _insert_filler(sentence)
            changes += int(changed)

        if random.random() < intensity * 0.45:
            sentence, changed = _insert_connector(sentence)
            changes += int(changed)

        if i < len(sentences) - 1 and random.random() < intensity * 0.25:
            merged, changed = _merge_with_next(sentence, sentences[i + 1])
            if changed:
                sentence = merged
                changes += 1
                i += 1

        processed.append(sentence.strip())
        i += 1

    # Force visible edits when randomness produced too few changes.
    if changes < min_changes and processed:
        for idx in range(len(processed)):
            if changes >= min_changes:
                break

            candidate = processed[idx]
            updated, changed = _swap_contraction(candidate)
            if not changed:
                updated, changed = _insert_filler(candidate)
            if not changed:
                updated, changed = _insert_connector(candidate)

            processed[idx] = updated
            changes += int(changed)

        while changes < min_changes:
            forced, _ = _insert_filler(processed[0])
            processed[0] = forced
            changes += 1

    return _normalize_ws(" ".join(processed))
