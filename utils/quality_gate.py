import re
from dataclasses import dataclass


_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "he",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
    "will",
    "with",
}


@dataclass
class QualityScore:
    total: float
    meaning_overlap: float
    diversity: float
    repetition_penalty: float
    sentence_variance: float
    length_ratio_score: float
    passed: bool


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _keywords(tokens: list[str]) -> set[str]:
    return {t for t in tokens if len(t) > 3 and t not in _STOPWORDS}


def _safe_divide(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return num / den


def score_candidate(source_text: str, candidate_text: str) -> QualityScore:
    source_tokens = _tokenize(source_text)
    candidate_tokens = _tokenize(candidate_text)

    if not source_tokens or not candidate_tokens:
        return QualityScore(0.0, 0.0, 0.0, 1.0, 0.0, 0.0, False)

    source_keywords = _keywords(source_tokens)
    candidate_keywords = _keywords(candidate_tokens)
    common_keywords = source_keywords & candidate_keywords

    meaning_overlap = _safe_divide(len(common_keywords), max(len(source_keywords), 1))

    unique_ratio = _safe_divide(len(set(candidate_tokens)), len(candidate_tokens))
    diversity = min(1.0, max(0.0, unique_ratio))

    top_freq = max(candidate_tokens.count(t) for t in set(candidate_tokens))
    repetition_penalty = _safe_divide(top_freq, len(candidate_tokens))

    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(candidate_text.strip()) if s.strip()]
    if len(sentences) < 2:
        sentence_variance = 0.2
    else:
        lengths = [len(_tokenize(s)) for s in sentences]
        avg = sum(lengths) / len(lengths)
        variance = sum((x - avg) ** 2 for x in lengths) / len(lengths)
        sentence_variance = min(1.0, variance / 35.0)

    length_ratio = _safe_divide(len(candidate_tokens), len(source_tokens))
    length_ratio_score = max(0.0, 1.0 - abs(length_ratio - 1.0))

    total = (
        (meaning_overlap * 0.45)
        + (diversity * 0.20)
        + ((1.0 - repetition_penalty) * 0.15)
        + (sentence_variance * 0.10)
        + (length_ratio_score * 0.10)
    )

    passed = (
        meaning_overlap >= 0.40
        and diversity >= 0.36
        and repetition_penalty <= 0.10
        and length_ratio >= 0.72
        and length_ratio <= 1.35
    )

    return QualityScore(
        total=round(total, 4),
        meaning_overlap=round(meaning_overlap, 4),
        diversity=round(diversity, 4),
        repetition_penalty=round(repetition_penalty, 4),
        sentence_variance=round(sentence_variance, 4),
        length_ratio_score=round(length_ratio_score, 4),
        passed=passed,
    )
