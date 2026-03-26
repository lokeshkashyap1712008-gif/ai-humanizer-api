import asyncio
import os
import google.generativeai as genai
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are an expert writing editor who rewrites AI-generated text to sound authentically human..."""

MODE_ADDITIONS = {
    "standard": "",
    "aggressive": " Heavily restructure every sentence.",
    "academic": " Maintain formal academic tone.",
    "casual": " Make it very conversational."
}


def get_model(plan: str):
    plan = plan.lower()
    if plan == "free":
        return "gemini-2.5-flash-lite", "gemini"
    elif plan == "basic":
        return "gemini-2.5-flash", "gemini"
    elif plan == "pro":
        return "claude-haiku-4-5-20251001", "claude"
    elif plan == "ultra":
        return "claude-sonnet-4-20250514", "claude"
    return "gemini-2.5-flash-lite", "gemini"


async def call_gemini(model_name, prompt):
    model = genai.GenerativeModel(model_name)
    response = await asyncio.to_thread(model.generate_content, prompt)
    return response.text


async def call_claude(model_name, prompt):
    response = await asyncio.to_thread(
        anthropic_client.messages.create,
        model=model_name,
        max_tokens=1000,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}
        }],
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


async def generate_humanized_text(text: str, mode: str, plan: str):
    model_name, provider = get_model(plan)

    prompt = SYSTEM_PROMPT + MODE_ADDITIONS.get(mode, "") + "\n\n" + text

    try:
        if provider == "gemini":
            return await asyncio.wait_for(call_gemini(model_name, prompt), timeout=30)
        else:
            return await asyncio.wait_for(call_claude(model_name, text), timeout=30)
    except asyncio.TimeoutError:
        raise Exception("timeout")
    except Exception:
        raise Exception("ai_error")