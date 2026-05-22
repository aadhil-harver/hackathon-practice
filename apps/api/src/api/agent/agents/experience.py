"""Experience Agent — qualitative strengths + concerns relative to the JD.

Parallel branch #3 of the fan-out. Writes ``strengths`` and ``concerns`` to state.
Deliberately *does not* re-do skill matching (that's the skill_match agent's job)
or score (that's the deterministic scorer's job) — focus is on contextual fit.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExperienceOutput(BaseModel):
    strengths: list[str] = Field(
        default_factory=list,
        description=(
            "3-5 short bullets naming qualitative fit signals — domain experience, "
            "scope of work, the kind of problems the candidate has solved. "
            "Each bullet must cite a SPECIFIC CV item, not a generic compliment."
        ),
    )
    concerns: list[str] = Field(
        default_factory=list,
        description=(
            "Misalignments worth surfacing: domain mismatch, work-style fit gaps, "
            "missing context for the role. Leave skill-level gaps to skill_match."
        ),
    )


EXPERIENCE_PROMPT = """You evaluate the QUALITATIVE fit of a candidate's experience
against a job description. The skill_match agent handles literal skill overlap
and the scorer handles the integer score — you are not doing either of those jobs.

Produce:

strengths (3-5 items):
- Things in the CV that make the candidate a strong fit for THIS JD specifically.
- Examples of valid strengths: same business domain, ownership of similar-scale
  systems, experience with the same kind of customers/users, prior roles at
  similar-stage companies, projects that map to the JD's day-to-day work.
- Every bullet must name a specific cv_profile item (project, domain, role).
  No generic praise.

concerns (can be empty, otherwise 1-4 items):
- QUALITATIVE misalignments, not skill gaps. Examples:
  - "All experience in agencies; JD is for an in-house team — different operating model."
  - "Healthcare-only domain experience; JD is fintech, which has different compliance constraints."
  - "Projects are all greenfield; this role inherits a 10-year-old codebase."
- Do NOT list missing skills (skill_match does that).
- Do NOT speculate about character, communication style, or non-CV-visible traits.

Be honest. A candidate with no concerns is rare and probably means you missed something."""
