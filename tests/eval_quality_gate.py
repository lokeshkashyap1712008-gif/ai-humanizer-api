import asyncio

from utils.ai_router import generate_humanized_text
from utils.quality_gate import score_candidate


SAMPLES = [
    "Time is valuable because once lost, it never returns, so we should use it wisely.",
    "Discipline helps people stay consistent with goals even when motivation is low.",
    "Technology improves efficiency, but misuse can create distraction and dependence.",
]


async def _run() -> None:
    print("Running quality-gate evaluation samples...")
    for idx, source in enumerate(SAMPLES, start=1):
        result = await generate_humanized_text(source, mode="standard", plan="pro")
        score = score_candidate(source, result.text)
        print(
            f"[{idx}] provider={result.provider_used} "
            f"score={score.total:.4f} passed={score.passed} "
            f"meaning={score.meaning_overlap:.4f} diversity={score.diversity:.4f}"
        )


if __name__ == "__main__":
    asyncio.run(_run())
