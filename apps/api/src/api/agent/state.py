from __future__ import annotations

from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class InterviewState(TypedDict):
    """State shared across every node in the interview-prep graph."""

    messages: Annotated[list, add_messages]
    """Conversation history. The ``add_messages`` reducer appends rather than replaces."""

    question_type: str | None
    """Classifier output: 'technical' | 'behavioral' | 'hr_career' | None."""

    coach_tips: str | None
    """Delivery-coach output, rendered separately and NOT re-fed into the graph."""