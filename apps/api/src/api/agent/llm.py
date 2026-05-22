"""Shared LLM factory.

Both the interview-prep graph and the CV-Screener graph call ``make_llm()`` to
construct an OpenRouter-backed ``ChatOpenAI`` with the same env contract:

- ``OPENROUTER_API_KEY``       — required
- ``INTERVIEW_MODEL``          — default ``anthropic/claude-sonnet-4.6``
- ``INTERVIEW_MAX_TOKENS``     — default ``800`` (load-bearing on low-credit accounts;
                                  OpenRouter rejects requests asking for the full
                                  65k token ceiling)
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

# LangSmith tracing — opt-in via env. If LANGSMITH_TRACING=true and
# LANGSMITH_API_KEY are set in .env, LangChain/LangGraph auto-send traces.
os.environ.setdefault("LANGSMITH_PROJECT", "interview-prep")


def make_llm(
    temperature: float = 0.3,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """Construct the shared OpenRouter chat model.

    ``temperature`` is exposed because deterministic-ish tasks (e.g. structured
    parsing) benefit from a lower value than open-ended generation.

    ``max_tokens`` overrides the ``INTERVIEW_MAX_TOKENS`` env default. Useful
    for agents that legitimately need more output budget (e.g. the interview
    questions agent has to emit ≥5 structured items, which exceeds what
    parser/skill_match need).
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to .env at the repo root. "
            "Get a key from https://openrouter.ai/keys"
        )

    effective_max_tokens = (
        max_tokens
        if max_tokens is not None
        else int(os.getenv("INTERVIEW_MAX_TOKENS", "800"))
    )

    return ChatOpenAI(
        model=os.getenv("INTERVIEW_MODEL", "anthropic/claude-sonnet-4.6"),
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        temperature=temperature,
        max_tokens=effective_max_tokens,
    )
