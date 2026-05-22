"""FastAPI router exposing the interview-prep graph.

Endpoints
---------
- ``POST /api/interview`` — full response, JSON body in/out.
- ``POST /api/interview/stream`` — same input, streams agent transitions and
  tokens as Server-Sent Events so the UI can show the graph executing live.

Both endpoints take a fresh single-turn message; multi-turn context is the
client's responsibility (the Streamlit UI rebuilds history from session_state
each turn — see ``apps/web/streamlit_app.py``).
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/interview", tags=["interview"])

# Node names emitted by the LangGraph stream — used to label SSE events.
_SPECIALIST_NODES = {"technical", "behavioral", "hr_career"}


# ── Request / Response schemas ────────────────────────────────────────────────


class InterviewRequest(BaseModel):
    message: str = Field(..., description="Latest user message / interview question")
    history: list[dict] = Field(
        default_factory=list,
        description=(
            "Prior chat turns as a list of ``{role, content}`` dicts. "
            "Reuse from your client-side session to give the graph multi-turn context."
        ),
    )
    thread_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Opaque identifier for this turn — surfaced in LangSmith metadata.",
    )


class InterviewResponse(BaseModel):
    thread_id: str
    question_type: str | None = None
    specialist_reply: str | None = None
    coach_tips: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_graph(request: Request):
    """Retrieve the compiled graph attached to the app state at startup."""
    return request.app.state.graph


def _build_graph_input(body: InterviewRequest) -> dict:
    """Construct the LangGraph input dict from request history + new message."""
    history = list(body.history) + [{"role": "user", "content": body.message}]
    return {"messages": history, "question_type": None, "coach_tips": None}


def _run_config(thread_id: str, surface: str) -> RunnableConfig:
    return {
        "run_name": "interview-turn",
        "tags": ["interview-prep", surface],
        "metadata": {"surface": surface, "thread_id": thread_id},
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", response_model=InterviewResponse, summary="Run the interview-prep graph once")
async def interview(body: InterviewRequest, request: Request):
    """Invoke the graph and return the complete result as JSON."""
    graph = _get_graph(request)
    result = await graph.ainvoke(
        _build_graph_input(body),
        config=_run_config(body.thread_id, "api"),
    )

    messages = result.get("messages") or []
    specialist_reply = None
    if messages:
        last = messages[-1]
        specialist_reply = last.content if hasattr(last, "content") else last.get("content")

    return InterviewResponse(
        thread_id=body.thread_id,
        question_type=result.get("question_type"),
        specialist_reply=specialist_reply,
        coach_tips=result.get("coach_tips"),
    )


@router.post("/stream", summary="Run the graph and stream agent events via SSE")
async def interview_stream(body: InterviewRequest, request: Request):
    """Stream the graph as Server-Sent Events.

    Event types
    -----------
    - ``agent``       — a new node started; data: ``{"node": "...", "question_type": "..."}``
    - ``token``       — a partial text chunk from the model
    - ``coach``       — the delivery-coach tips (one event per turn)
    - ``done``        — final event; data: ``{"thread_id": "..."}``
    - ``error``       — data: ``{"detail": "..."}``
    """
    graph = _get_graph(request)
    graph_input = _build_graph_input(body)
    config = _run_config(body.thread_id, "api-stream")

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            current_question_type: str | None = None

            async for event in graph.astream_events(graph_input, config=config, version="v2"):
                kind = event["event"]
                name = event.get("name", "")

                if kind == "on_chain_start" and name in (
                    "classifier",
                    "router",
                    *_SPECIALIST_NODES,
                    "coach",
                ):
                    yield {
                        "event": "agent",
                        "data": json.dumps(
                            {"node": name, "question_type": current_question_type}
                        ),
                    }

                if kind == "on_chain_end" and name == "classifier":
                    output = event["data"].get("output") or {}
                    current_question_type = output.get("question_type")

                if kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk and chunk.content:
                        yield {
                            "event": "token",
                            "data": json.dumps({"token": chunk.content}),
                        }

                if kind == "on_chain_end" and name == "coach":
                    output = event["data"].get("output") or {}
                    tips = output.get("coach_tips")
                    if tips:
                        yield {"event": "coach", "data": json.dumps({"coach_tips": tips})}

            yield {"event": "done", "data": json.dumps({"thread_id": body.thread_id})}
        except Exception as exc:
            logger.exception("Error during interview stream")
            yield {"event": "error", "data": json.dumps({"detail": str(exc)})}

    return EventSourceResponse(event_generator())