"""Seniority Agent — assesses candidate seniority from the parsed profile.

Parallel branch #2 of the fan-out. Writes ``assessed_seniority`` and
``seniority_evidence`` to state.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SeniorityOutput(BaseModel):
    assessed_seniority: Literal["junior", "mid", "senior"] = Field(
        ...,
        description=(
            "The candidate's actual seniority based on their CV — independent of "
            "what the JD asks for. The scorer compares this against jd_profile.target_seniority."
        ),
    )
    seniority_evidence: list[str] = Field(
        default_factory=list,
        description=(
            "2-3 short bullets citing specific CV items that drove the call. "
            "Each bullet should name a project, role, or year-count from the parsed profile — "
            "not a generic justification."
        ),
    )


SENIORITY_PROMPT = """You assess a candidate's seniority based on their parsed CV.

Rules:
- 'junior'  : 0-2 years experience OR no leadership/ownership signals OR scope limited
              to small features under guidance.
- 'mid'     : 3-5 years OR clear ownership of components / small projects without managing
              others, but still operating within a team's scope.
- 'senior'  : 6+ years OR leadership/architecture/cross-team-influence signals (tech lead,
              owning systems end-to-end, mentoring, designing for scale).

Important:
- The JD's *target* seniority is in jd_profile.target_seniority for context. Your job is
  to assess what the candidate ACTUALLY is, not whether they match. The scorer compares
  assessed_seniority vs target_seniority.
- Be willing to call 'senior' even when the candidate would be considered 'mid' for the
  JD's role — and vice versa. Honesty here is more useful than alignment.

seniority_evidence (2-3 bullets):
- Each bullet must cite a SPECIFIC item from cv_profile (a project, a role, a year count).
- Generic statements ("strong technical background") are not evidence. Cut them."""
