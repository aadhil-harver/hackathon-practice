from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class QuestionClassifier(BaseModel):
    """Structured output schema for the classifier node."""

    question_type: Literal["technical", "behavioral", "hr_career"] = Field(
        ...,
        description=(
            "Classify the interview question as 'technical' (coding, DSA, system design, "
            "language-specific), 'behavioral' (tell-me-about-a-time, STAR-style), or "
            "'hr_career' (why this company, salary, strengths/weaknesses, career goals)."
        ),
    )


CLASSIFIER_PROMPT = """You classify the user's LATEST interview-prep message into one of three buckets.

        STEP 1 — Decide if the latest message is a STANDALONE question or a FOLLOW-UP.
        It is a follow-up if it does any of the following with respect to prior turns:
          - refines the role/context (e.g. "this role is more business-focused",
            "actually it's a backend position", "for a junior level")
          - asks for adjustment of the previous answer (e.g. "make it shorter",
            "give me another example", "try again", "go deeper")
          - is a short fragment that only makes sense in context

        If it is a FOLLOW-UP, classify it using the TOPIC of the most recent
        substantive user question, NOT the follow-up text alone. Stick with the
        prior bucket unless the user has clearly switched topic.

        STEP 2 — Pick the bucket:
        - 'technical': coding, data structures, algorithms, SQL, system design,
          language/framework specifics, debugging, technical trade-offs, analytical
          case questions, data-analysis methodology.
        - 'behavioral': "tell me about a time...", teamwork, conflict, leadership,
          failure/learning stories, anything best answered with STAR.
        - 'hr_career': company fit, motivation, salary expectations,
          strengths/weaknesses, career goals, "why this role", general HR screening.

        Return ONLY the bucket name."""
