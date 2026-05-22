"""Compiled LangGraph for the interview-prep workflow.

Pipeline:

    START -> classifier -> router -> (technical | behavioral | hr_career) -> coach -> END

The shape is the original three-specialist + delivery-coach setup, lifted out of
``interview.py`` and split into per-agent prompt modules plus this orchestration
file. ``build_graph()`` is the factory the FastAPI lifespan and the Streamlit UI
both call; a module-level ``graph`` instance is also exposed for backwards
compatibility with ``from api.agent.graph import graph`` callers.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from api.agent.agents.behavioral import BEHAVIORAL_PROMPT
from api.agent.agents.classifier import CLASSIFIER_PROMPT, QuestionClassifier
from api.agent.agents.coach import COACH_PROMPT
from api.agent.agents.hr_career import HR_CAREER_PROMPT
from api.agent.agents.technical import TECHNICAL_PROMPT
from api.agent.state import InterviewState

load_dotenv()

# LangSmith tracing — opt-in via env. If LANGSMITH_TRACING=true and
# LANGSMITH_API_KEY are set in .env, LangChain/LangGraph auto-send traces.
# Default the project name here so traces land in "interview-prep" instead of
# the catch-all "default" project. Users can override via LANGSMITH_PROJECT.
os.environ.setdefault("LANGSMITH_PROJECT", "interview-prep")


def _make_llm() -> ChatOpenAI:
    """Construct the OpenRouter-backed chat model used by every node.

    OpenRouter is OpenAI-compatible: point ``ChatOpenAI`` at its base_url and
    use ``OPENROUTER_API_KEY``. Default model is Claude Sonnet 4.6 (strongest
    Sonnet currently on OpenRouter); override with ``INTERVIEW_MODEL``.
    """
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to .env at the repo root. "
            "Get a key from https://openrouter.ai/keys"
        )

    # OpenRouter enforces an upper-bound check against remaining credit. Without
    # this cap, ChatOpenAI sends max_tokens=<model max> (65536 on Sonnet 4.6),
    # which low-credit accounts cannot afford. Our prompts target ~350 words, so
    # 800 is comfortable headroom.
    return ChatOpenAI(
        model=os.getenv("INTERVIEW_MODEL", "anthropic/claude-sonnet-4.6"),
        base_url="https://openrouter.ai/api/v1",
        api_key=openrouter_api_key,
        temperature=0.3,
        max_tokens=int(os.getenv("INTERVIEW_MAX_TOKENS", "800")),
    )


def _history_as_dicts(messages):
    """Convert LangChain message objects into role/content dicts for LLM calls."""
    out = []
    for msg in messages:
        role = "user" if getattr(msg, "type", None) == "human" else "assistant"
        out.append({"role": role, "content": msg.content})
    return out


def build_graph():
    """Build and compile the interview-prep StateGraph.

    Returns a compiled LangGraph ``CompiledGraph``. Called once at app startup
    (FastAPI lifespan) and again when the Streamlit app imports the graph.
    """
    llm = _make_llm()

    # ── Node functions ───────────────────────────────────────────────────

    def classify_question(state: InterviewState):
        classifier_llm = llm.with_structured_output(QuestionClassifier)
        history = _history_as_dicts(state["messages"])
        system_msg = {"role": "system", "content": CLASSIFIER_PROMPT}
        result = classifier_llm.invoke([system_msg] + history)
        return {"question_type": result.question_type}

    def router(state: InterviewState):
        question_type = state.get("question_type", "hr_career")
        return {"next": question_type}

    def technical_agent(state: InterviewState):
        history = _history_as_dicts(state["messages"])
        system_msg = {"role": "system", "content": TECHNICAL_PROMPT}
        reply = llm.invoke([system_msg] + history)
        return {"messages": [{"role": "assistant", "content": reply.content}]}

    def behavioral_agent(state: InterviewState):
        history = _history_as_dicts(state["messages"])
        system_msg = {"role": "system", "content": BEHAVIORAL_PROMPT}
        reply = llm.invoke([system_msg] + history)
        return {"messages": [{"role": "assistant", "content": reply.content}]}

    def hr_career_agent(state: InterviewState):
        history = _history_as_dicts(state["messages"])
        system_msg = {"role": "system", "content": HR_CAREER_PROMPT}
        reply = llm.invoke([system_msg] + history)
        return {"messages": [{"role": "assistant", "content": reply.content}]}

    def coach_agent(state: InterviewState):
        latest_user_question = ""
        for msg in reversed(state["messages"]):
            if getattr(msg, "type", None) == "human":
                latest_user_question = msg.content
                break
        specialist_reply = state["messages"][-1].content if state["messages"] else ""

        messages = [
            {"role": "system", "content": COACH_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Interview question:\n{latest_user_question}\n\n"
                    f"Specialist's model answer:\n{specialist_reply}"
                ),
            },
        ]
        reply = llm.invoke(messages)
        return {"coach_tips": reply.content}

    # ── Graph assembly ───────────────────────────────────────────────────

    builder = StateGraph(InterviewState)

    builder.add_node("classifier", classify_question)
    builder.add_node("router", router)
    builder.add_node("technical", technical_agent)
    builder.add_node("behavioral", behavioral_agent)
    builder.add_node("hr_career", hr_career_agent)
    builder.add_node("coach", coach_agent)

    builder.add_edge(START, "classifier")
    builder.add_edge("classifier", "router")

    builder.add_conditional_edges(
        "router",
        lambda state: state.get("next"),
        {
            "technical": "technical",
            "behavioral": "behavioral",
            "hr_career": "hr_career",
        },
    )

    builder.add_edge("technical", "coach")
    builder.add_edge("behavioral", "coach")
    builder.add_edge("hr_career", "coach")
    builder.add_edge("coach", END)

    return builder.compile()


# Module-level compiled graph — convenient for callers that don't need to pass
# arguments (e.g. the Streamlit UI). The FastAPI app calls ``build_graph()``
# inside its lifespan instead so it can swap in a checkpointer.
graph = build_graph()
