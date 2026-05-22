"""State schemas for the two graphs in this repo.

- ``InterviewState`` — interview-prep workflow (current production).
- ``ScreeningState`` — CV-Screener workflow (in build; see CLAUDE.md > Build order).
"""

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


class ScreeningState(TypedDict, total=False):
    """State shared across every node in the CV-Screener graph.

    ``total=False`` because nodes populate fields incrementally — early in the
    pipeline most fields are still ``None``. Reads should always tolerate
    missing keys via ``state.get(...)``.

    Each downstream node writes to a **disjoint** set of keys so the parallel
    fan-out (skill_match / seniority / experience) never conflicts on merge.
    """

    # ── Inputs (set by input_handler) ───────────────────────────────────────
    cv_text: str
    """Raw CV text after normalisation."""

    jd_text: str
    """Raw job-description text after normalisation."""

    # ── Parser output ───────────────────────────────────────────────────────
    cv_profile: dict | None
    """Parsed candidate profile: ``{skills, years_experience, projects, domains, education}``."""

    jd_profile: dict | None
    """Parsed job description: ``{required_skills, nice_to_have, target_seniority, domain}``."""

    parse_confidence: float | None
    """0.0–1.0. Drives confidence gate #1."""

    # ── Skill Match (parallel) ──────────────────────────────────────────────
    matched_skills: list[dict] | None
    """``[{skill, kind: 'required'|'nice_to_have'}, ...]`` — only skills present in CV."""

    missing_skills: list[str] | None
    """Required JD skills the candidate does NOT have."""

    # ── Seniority (parallel) ────────────────────────────────────────────────
    assessed_seniority: str | None
    """'junior' | 'mid' | 'senior'."""

    seniority_evidence: list[str] | None
    """2-3 bullets citing specific CV items that drove the seniority call."""

    # ── Experience (parallel) ───────────────────────────────────────────────
    strengths: list[str] | None
    """Qualitative fit strengths (3-5 items). NOT a skill list — skill_match owns that."""

    concerns: list[str] | None
    """Qualitative misalignments (domain mismatch, level gap, etc.)."""

    # ── Integrity & Fairness ────────────────────────────────────────────────
    gaps: list[str] | None
    """Employment / education / skill gaps worth surfacing to the recruiter."""

    inconsistencies: list[str] | None
    """Self-contradictions or claims that don't square with each other."""

    bias_flags: list[str] | None
    """Possible bias signals — recruiter decides; the agent flags only."""

    risk_confidence: float | None
    """0.0–1.0. **HIGH = profile is clean (low risk); LOW = significant concerns.**
    Symmetric with ``parse_confidence``: in both cases higher = better. Confidence
    gate #2 routes to human review when this drops below threshold."""

    # ── Scorer + Recommendation (deterministic Python, not LLM) ─────────────
    score: int | None
    """0-10. Weighted: 0.4·skills + 0.3·seniority + 0.2·domain + 0.1·education."""

    score_breakdown: dict | None
    """``{skill_subscore, seniority_subscore, domain_subscore, education_subscore, weights}``
    so the recruiter UI can show *why* the score is what it is. Populated by the
    deterministic scorer alongside ``score``."""

    recommendation: str | None
    """'Shortlist' | 'Hold' | 'Reject' — pure mapping from ``score``."""

    # ── Interview Questions (skipped on Reject) ─────────────────────────────
    questions: list[dict] | None
    """``[{area, question, why_asked}, ...]`` — ≥5 when present."""

    # ── HITL gate flags ─────────────────────────────────────────────────────
    force_pass_gate_1: bool
    """Set by the Streamlit Approve button to bypass conf_gate_1 on resume."""

    force_pass_gate_2: bool
    """Set by the Streamlit Approve button to bypass conf_gate_2 on resume."""

    review_stage: str | None
    """``'gate_1'`` / ``'gate_2'`` / ``None``. Set by ``human_review_*`` sink
    nodes so the Streamlit UI can detect that the graph terminated early at a
    HITL gate (vs. running to completion). Cleared by the UI on resume."""
