import random
import re


def humanize_post_process(text: str) -> str:
    if not text or not text.strip():
        return ""

    sentences = [segment.strip() for segment in re.findall(r"[^.!?]+[.!?]*", text) if segment and segment.strip()]
    if not sentences:
        return re.sub(r"\s{2,}", " ", text).strip()

    processed = []
    i = 0

    while i < len(sentences):
        sentence = sentences[i]

        if random.random() < 0.10:
            sentence = re.sub(r",\s+", " ", sentence, count=1)

        if random.random() < 0.10:
            sentence = re.sub(r"\b(and|but|so)\b", "", sentence, count=1, flags=re.IGNORECASE)

        if random.random() < 0.10:
            if not re.match(r"^(and|but|so)\b", sentence.strip(), flags=re.IGNORECASE):
                sentence = f"{random.choice(['And ', 'But ', 'So '])}{sentence.lstrip()}"

        if random.random() < 0.10:
            filler = random.choice([" kind of", " maybe", " I guess", " a bit"])
            sentence = sentence.rstrip()
            if sentence.endswith((".", "!", "?")):
                sentence = f"{sentence[:-1]}{filler}{sentence[-1]}"
            else:
                sentence = f"{sentence}{filler}"

        if len(sentence) > 80 and random.random() < 0.15:
            midpoint = len(sentence) // 2
            left_space = sentence.rfind(" ", 0, midpoint)
            right_space = sentence.find(" ", midpoint)
            split_at = left_space if left_space != -1 else right_space
            if split_at == -1:
                split_at = midpoint

            first = sentence[:split_at].strip()
            second = sentence[split_at:].strip()

            if first and second:
                if first[-1] not in ".!?":
                    first = f"{first}."
                sentence = f"{first} {second}"

        if i < len(sentences) - 1 and random.random() < 0.10:
            next_sentence = sentences[i + 1].strip()
            if next_sentence:
                if len(next_sentence) > 1:
                    next_sentence = f"{next_sentence[0].lower()}{next_sentence[1:]}"
                else:
                    next_sentence = next_sentence.lower()

                sentence = sentence.rstrip()
                if sentence.endswith((".", "!", "?")):
                    sentence = sentence[:-1]
                sentence = f"{sentence} {next_sentence}".strip()
                i += 1

        processed.append(sentence.strip())
        i += 1

    final_text = " ".join(processed)
    final_text = re.sub(r"\s{2,}", " ", final_text).strip()
    return final_text
