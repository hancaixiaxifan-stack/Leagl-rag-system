from __future__ import annotations

import re

from openai import OpenAI

from .settings import settings


class LLMAuthError(RuntimeError):
    """Raised when the LLM API key is missing or invalid."""


def _client() -> OpenAI:
    if not settings.deepseek_api_key:
        raise LLMAuthError(
            "Missing DEEPSEEK_API_KEY. Set env var DEEPSEEK_API_KEY for chat completion."
        )
    return OpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        timeout=settings.deepseek_timeout_s,
        max_retries=settings.deepseek_max_retries,
    )


def chat_answer(system: str, user: str, max_tokens: int | None = None) -> str:
    """DeepSeek OpenAI-compatible chat completions.

    Args:
        max_tokens: 覆盖默认的 answer_max_tokens，用于需要更长输出的场景。
    """
    c = _client()
    resp = c.chat.completions.create(
        model=settings.deepseek_chat_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=settings.temperature,
        max_tokens=max_tokens if max_tokens is not None else settings.answer_max_tokens,
        extra_body={"thinking": {"type": "disabled"}},
    )
    msg = resp.choices[0].message
    content = msg.content or ""

    # Fallback: DeepSeek thinking mode may put answer in reasoning_content
    if not content and hasattr(msg, "reasoning_content") and msg.reasoning_content:
        content = msg.reasoning_content

    # Strip thinking/reasoning tags from DeepSeek-R1/V4 and similar models
    content = re.sub(r"<redacted_thinking>[\s\S]*?</redacted_thinking>", "", content, flags=re.I).strip()
    content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.I).strip()
    return content
