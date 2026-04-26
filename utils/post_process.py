import random
import re
from typing import List, Tuple

_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)")

MODE_FACTOR = {
    "standard": 0.6,
    "aggressive": 1.0,
    "academic": 0.5,
    "casual": 0.85,
}

def _p(base, mode):
    return min(1.0, base * MODE_FACTOR.get(mode, 0.7))


def _normalize(text: str) -> str:
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r" ([.,!?;:])", r"\1", text)
    return text.strip()


def _split(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_RE.findall(text) if s.strip()]


# ============================
# SYNONYM / PHRASE SWAPS
# ============================

# AI models heavily overuse these words — swap them out
AI_OVERUSED = {
    r"\bfurthermore\b": ["beyond that", "on top of this", "and also", "plus"],
    r"\bmoreover\b": ["what's more", "also", "besides", "and then there's"],
    r"\badditionally\b": ["also", "on top of that", "plus", "and"],
    r"\bin conclusion\b": ["all in all", "when it's all said and done", "at the end of the day", "so"],
    r"\bultimately\b": ["in the end", "at the end of the day", "when all is said and done", "really"],
    r"\bit is important to note\b": ["worth noting", "keep in mind", "notably", "notably enough"],
    r"\bit is worth noting\b": ["worth mentioning", "notably", "and notably"],
    r"\bone must consider\b": ["you have to think about", "it's worth considering", "consider"],
    r"\bthis is because\b": ["the reason is", "that's because", "since", "because"],
    r"\bin today's society\b": ["these days", "nowadays", "today", "in our world today"],
    r"\bin today's world\b": ["these days", "nowadays", "in our current era"],
    r"\bdelve into\b": ["dig into", "explore", "look into", "examine", "get into"],
    r"\bdelves into\b": ["digs into", "explores", "looks into", "examines"],
    r"\bsignificant\b": ["major", "big", "real", "notable", "substantial", "key"],
    r"\bsignificantly\b": ["greatly", "a lot", "considerably", "quite a bit", "markedly"],
    r"\bsubstantial\b": ["large", "considerable", "real", "sizable", "major"],
    r"\bsubstantially\b": ["considerably", "largely", "by a lot", "greatly"],
    r"\bfacilitate\b": ["help", "support", "enable", "make easier", "drive"],
    r"\butilize\b": ["use", "rely on", "work with", "employ"],
    r"\butilizes\b": ["uses", "relies on", "works with"],
    r"\bcomprehensive\b": ["thorough", "full", "complete", "wide-ranging", "broad"],
    r"\bfoster\b": ["build", "grow", "encourage", "nurture", "support"],
    r"\bfosters\b": ["builds", "grows", "encourages", "nurtures"],
    r"\bemphasize\b": ["stress", "highlight", "point out", "make clear"],
    r"\bemphasizes\b": ["stresses", "highlights", "points out", "makes clear"],
    r"\bcrucial\b": ["key", "vital", "critical", "essential", "important"],
    r"\bparamount\b": ["top priority", "critical", "most important", "key"],
    r"\bindeed\b": ["in fact", "really", "actually", "yes", "truly"],
    r"\bnevertheless\b": ["still", "even so", "that said", "but"],
    r"\bnonetheless\b": ["still", "even so", "that said", "but"],
    r"\bconsequently\b": ["as a result", "so", "because of this", "therefore"],
    r"\bthus\b": ["so", "as a result", "because of this", "hence"],
    r"\bhence\b": ["so", "that's why", "as a result", "therefore"],
    r"\btherefore\b": ["so", "for this reason", "as a result", "that's why"],
    r"\bin order to\b": ["to", "so as to", "with the goal of"],
    r"\bdue to the fact that\b": ["because", "since", "given that"],
    r"\bwith regard to\b": ["regarding", "about", "when it comes to", "on"],
    r"\bwith respect to\b": ["regarding", "about", "when it comes to", "on"],
    r"\bin terms of\b": ["regarding", "when it comes to", "as for", "about"],
    r"\bplays a (crucial|key|vital|important|significant) role\b": ["is central to", "matters a lot for", "drives", "shapes", "is key to"],
    r"\bit should be noted\b": ["notably", "worth noting", "keep in mind"],
    r"\bit is evident that\b": ["clearly", "it's clear that", "obviously", "evidently"],
    r"\bit is clear that\b": ["clearly", "obviously", "evidently", "plainly"],
    r"\bpivotal\b": ["key", "central", "critical", "defining"],
    r"\binvaluable\b": ["very valuable", "essential", "priceless", "critical"],
    r"\bprofound\b": ["deep", "serious", "major", "significant"],
    r"\bexacerbate\b": ["worsen", "make worse", "aggravate", "intensify"],
    r"\bexacerbates\b": ["worsens", "makes worse", "aggravates", "intensifies"],
    r"\bmitigate\b": ["reduce", "lessen", "ease", "soften", "curb"],
    r"\bmitigates\b": ["reduces", "lessens", "eases", "softens"],
    r"\blandscape\b": ["field", "world", "space", "area", "environment"],
    r"\bparadigm\b": ["model", "framework", "approach", "way of thinking"],
    r"\bsynergy\b": ["collaboration", "teamwork", "combined effect"],
    r"\boptimal\b": ["best", "ideal", "most effective", "top"],
    r"\brobust\b": ["strong", "solid", "sturdy", "reliable", "powerful"],
    r"\bnuanced\b": ["complex", "subtle", "layered", "detailed"],
    r"\bintersect\b": ["meet", "overlap", "cross", "connect"],
    r"\bintersects\b": ["meets", "overlaps", "crosses", "connects"],
    r"\bunderscores\b": ["highlights", "shows", "points to", "makes clear"],
    r"\bunderscore\b": ["highlight", "show", "point to", "make clear"],
}

# Transition phrases AI uses at sentence starts
AI_SENTENCE_STARTERS = {
    r"^In summary[,.]?\s*": ["So,", "To wrap up,", "Putting it all together,", "In short,", "All in all,"],
    r"^To summarize[,.]?\s*": ["So,", "In short,", "Basically,", "The short version:"],
    r"^In conclusion[,.]?\s*": ["So,", "All in all,", "At the end of the day,", "When it comes down to it,"],
    r"^It is (important|essential|crucial|vital) to (note|understand|recognize)\b[,.]?\s*": [
        "Worth noting:", "Keep in mind:", "Importantly,", "One thing that matters here:"],
    r"^This (essay|paper|article|piece) (will|aims to|seeks to|explores?)\b": [
        "Here,", "What follows is", "The focus here is on", "This piece looks at"],
    r"^(Firstly|Secondly|Thirdly|Lastly|Finally)[,.]?\s*": [],  # handled separately
}


def _swap_overused(text: str, mode: str) -> str:
    for pattern, replacements in AI_OVERUSED.items():
        if not replacements:
            continue
        compiled = re.compile(pattern, re.IGNORECASE)
        def _replace(m, reps=replacements, md=mode):
            if random.random() < _p(0.85, md):
                replacement = random.choice(reps)
                # preserve capitalisation
                original = m.group()
                if original and original[0].isupper():
                    replacement = replacement[0].upper() + replacement[1:]
                return replacement
            return m.group()
        text = compiled.sub(_replace, text)
    return text


def _swap_sentence_starters(sentence: str, mode: str) -> str:
    for pattern, replacements in AI_SENTENCE_STARTERS.items():
        m = re.match(pattern, sentence, re.IGNORECASE)
        if m and replacements and random.random() < _p(0.8, mode):
            replacement = random.choice(replacements)
            sentence = replacement + " " + sentence[m.end():]
            break
    return sentence


# ============================
# CONTRACTION INJECTION
# ============================

CONTRACTIONS = [
    (r"\bit is\b", "it's"),
    (r"\bthat is\b", "that's"),
    (r"\bthey are\b", "they're"),
    (r"\bwe are\b", "we're"),
    (r"\byou are\b", "you're"),
    (r"\bI am\b", "I'm"),
    (r"\bhe is\b", "he's"),
    (r"\bshe is\b", "she's"),
    (r"\bdoes not\b", "doesn't"),
    (r"\bdo not\b", "don't"),
    (r"\bdid not\b", "didn't"),
    (r"\bwill not\b", "won't"),
    (r"\bwould not\b", "wouldn't"),
    (r"\bcould not\b", "couldn't"),
    (r"\bshould not\b", "shouldn't"),
    (r"\bcannot\b", "can't"),
    (r"\bhave not\b", "haven't"),
    (r"\bhas not\b", "hasn't"),
    (r"\bhad not\b", "hadn't"),
    (r"\bwas not\b", "wasn't"),
    (r"\bwere not\b", "weren't"),
    (r"\bthere is\b", "there's"),
    (r"\bthere are\b", "there are"),  # no contraction, but flag to keep
    (r"\bwhat is\b", "what's"),
    (r"\bwho is\b", "who's"),
    (r"\bthat would\b", "that'd"),
    (r"\bI would\b", "I'd"),
    (r"\bI will\b", "I'll"),
    (r"\bI have\b", "I've"),
    (r"\bthey have\b", "they've"),
    (r"\bwe have\b", "we've"),
    (r"\byou have\b", "you've"),
]

_CONTRACTION_COMPILED = [(re.compile(p, re.IGNORECASE), r) for p, r in CONTRACTIONS]

def _inject_contractions(text: str, mode: str) -> str:
    # Academic mode: fewer contractions
    prob = _p(0.75, mode) if mode != "academic" else _p(0.25, mode)
    for pattern, replacement in _CONTRACTION_COMPILED:
        def _replace(m, rep=replacement, p=prob):
            if random.random() < p:
                orig = m.group()
                if orig[0].isupper():
                    return rep[0].upper() + rep[1:]
                return rep
            return m.group()
        text = pattern.sub(_replace, text)
    return text


# ============================
# SENTENCE RHYTHM VARIATION
# ============================

FILLER_PHRASES = [
    "Honestly,", "Look,", "Here's the thing —", "To be fair,",
    "Think about it:", "The reality is,", "At its core,",
    "In practice,", "Put simply,", "The truth is,",
]

HEDGE_PHRASES = [
    "in many ways", "to some extent", "for the most part",
    "in most cases", "generally speaking", "by and large",
    "more often than not", "on the whole",
]

AFTERTHOUGHT_PHRASES = [
    "— and that matters.", "— which is saying something.", 
    "— at least in most cases.", "— a point worth keeping in mind.",
    ", and it shows.", ", which shouldn't be overlooked.",
]


def _vary_sentence_length(sentences: List[str], mode: str) -> List[str]:
    """Mix long and short sentences — humans rarely write uniform-length sentences."""
    out = []
    i = 0
    while i < len(sentences):
        s = sentences[i]
        words = s.split()

        # Merge two short sentences occasionally
        if (len(words) < 8 and i + 1 < len(sentences)
                and random.random() < _p(0.3, mode)):
            next_s = sentences[i + 1]
            connectors = [", and", ", but", "; and", " — though", ", so", ", while"]
            connector = random.choice(connectors)
            merged = s.rstrip(".!?") + connector + " " + next_s[0].lower() + next_s[1:]
            out.append(merged)
            i += 2
            continue

        # Split very long sentences
        if len(words) > 20 and random.random() < _p(0.5, mode):
            cut = random.randint(8, len(words) - 6)
            part1 = " ".join(words[:cut]).rstrip(",")
            part2 = " ".join(words[cut:])
            if not part1.endswith((".", "!", "?")):
                part1 += "."
            part2 = part2[0].upper() + part2[1:]
            out.append(part1)
            out.append(part2)
            i += 1
            continue

        out.append(s)
        i += 1
    return out


def _add_filler_opener(sentence: str, mode: str) -> str:
    """Add conversational opener to some sentences."""
    if random.random() < _p(0.12, mode):
        filler = random.choice(FILLER_PHRASES)
        # Don't double-up if sentence already has a natural opener
        if not re.match(r"^(So|But|And|Yet|Still|Also|Look|Honestly)[,\s]", sentence):
            return filler + " " + sentence[0].lower() + sentence[1:]
    return sentence


def _add_hedge(sentence: str, mode: str) -> str:
    """Insert a hedge phrase into a sentence at a natural point."""
    if mode == "aggressive" and random.random() < 0.15:
        words = sentence.split()
        if len(words) > 6:
            insert_pos = random.randint(3, min(7, len(words) - 2))
            hedge = random.choice(HEDGE_PHRASES)
            words.insert(insert_pos, hedge + ",")
            return " ".join(words)
    return sentence


def _add_afterthought(sentence: str, mode: str) -> str:
    """Append a brief afterthought to add personality."""
    if random.random() < _p(0.08, mode) and sentence.endswith("."):
        afterthought = random.choice(AFTERTHOUGHT_PHRASES)
        return sentence[:-1] + afterthought
    return sentence


# ============================
# STRUCTURAL REWRITES
# ============================

def _passive_to_active_hints(sentence: str, mode: str) -> str:
    """Replace some passive constructions with more active equivalents."""
    replacements = [
        (r"\bcan be seen\b", random.choice(["shows", "reveals", "demonstrates", "illustrates"])),
        (r"\bhas been shown\b", random.choice(["research shows", "studies show", "evidence shows"])),
        (r"\bhas been found\b", random.choice(["research finds", "findings show", "evidence suggests"])),
        (r"\bis believed to\b", random.choice(["many think", "experts believe", "it's thought that"])),
        (r"\bwas found to\b", random.choice(["turned out to", "proved to", "showed it could"])),
        (r"\bcan be achieved\b", random.choice(["is achievable", "works if", "happens when"])),
        (r"\bshould be noted\b", random.choice(["worth noting", "note that", "keep in mind"])),
        (r"\bmust be considered\b", random.choice(["needs consideration", "deserves attention", "is worth thinking about"])),
    ]
    for pattern, replacement in replacements:
        if random.random() < _p(0.7, mode):
            sentence = re.sub(pattern, replacement, sentence, flags=re.IGNORECASE, count=1)
    return sentence


def _vary_punctuation(sentence: str, mode: str) -> str:
    """Occasionally swap period endings for em dashes or add parentheticals."""
    if random.random() < _p(0.06, mode) and sentence.endswith("."):
        # Convert to em-dash trailing clause style — no additional content needed
        pass  # Reserved for future clause injection
    return sentence


# ============================
# NUMBERED LIST NATURALISATION
# ============================

_LIST_STARTERS = re.compile(
    r"^(\d+[.)]\s+|[-•–]\s+|[Ff]irst(?:ly)?[,.]?\s+|[Ss]econd(?:ly)?[,.]?\s+|"
    r"[Tt]hird(?:ly)?[,.]?\s+|[Ll]ast(?:ly)?[,.]?\s+|[Ff]inally[,.]?\s+)"
)

LIST_CONNECTORS = [
    "To start with,", "For one thing,", "One key point:", "Right off the bat,",
    "On top of that,", "Beyond that,", "Building on this,", "There's also",
    "Crucially,", "And finally,", "To close,",
]

def _denumber_lists(sentences: List[str], mode: str) -> List[str]:
    """Replace robotic numbered lists with natural connectors."""
    out = []
    connector_idx = 0
    for s in sentences:
        m = _LIST_STARTERS.match(s)
        if m and random.random() < _p(0.8, mode):
            remainder = s[m.end():]
            if connector_idx < len(LIST_CONNECTORS):
                connector = LIST_CONNECTORS[connector_idx]
                connector_idx += 1
            else:
                connector = random.choice(["Also,", "And,", "Plus,", "Then,"])
            s = connector + " " + remainder[0].lower() + remainder[1:]
        else:
            connector_idx = 0  # reset on non-list sentence
        out.append(s)
    return out


# ============================
# BURSTINESS (Rhythm Breaks)
# ============================

def _insert_short_punchy(sentences: List[str], mode: str) -> List[str]:
    """
    Humans naturally write 1-3 word punchy sentences between longer ones.
    This is one of the strongest human writing signals.
    """
    punchy_inserts = [
        "And it works.", "Simple as that.", "Really.", "That's the key.",
        "It's worth thinking about.", "This matters.", "Not always, though.",
        "The evidence is clear.", "But not everyone agrees.", "It's complicated.",
        "That changes things.", "Worth considering.", "Go figure.",
    ]
    out = []
    for i, s in enumerate(sentences):
        out.append(s)
        # Insert a punchy sentence every ~6 sentences with probability
        if (i > 0 and i % random.randint(5, 8) == 0
                and random.random() < _p(0.35, mode)):
            out.append(random.choice(punchy_inserts))
    return out


# ============================
# MAIN FUNCTION
# ============================

def humanize_post_process(text: str, mode: str = "standard") -> str:
    if not text:
        return text

    # Phase 1: Word-level substitutions on full text
    text = _swap_overused(text, mode)
    text = _inject_contractions(text, mode)
    text = _passive_to_active_hints(text, mode)

    # Phase 2: Sentence-level work
    sentences = _split(text)
    if not sentences:
        return text

    # Replace list numbering with natural connectors
    sentences = _denumber_lists(sentences, mode)

    # Vary sentence length (merge short, split long)
    sentences = _vary_sentence_length(sentences, mode)

    # Per-sentence transforms
    out = []
    for sentence in sentences:
        sentence = _swap_sentence_starters(sentence, mode)
        sentence = _add_filler_opener(sentence, mode)
        sentence = _add_hedge(sentence, mode)
        sentence = _add_afterthought(sentence, mode)
        sentence = _vary_punctuation(sentence, mode)
        out.append(sentence.strip())

    # Phase 3: Structural rhythm — inject punchy sentences
    out = _insert_short_punchy(out, mode)

    return _normalize(" ".join(out))