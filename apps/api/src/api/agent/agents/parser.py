"""Parsing Agent — extracts structured profiles from raw CV + JD text.

Owns confidence gate #1's input signal: ``parse_confidence`` flows into
``conf_gate_1`` and decides whether the pipeline pauses for human review.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CVProfile(BaseModel):
    candidate_name: str | None = Field(
        None,
        description=(
            "Full name as it appears at the top of the CV. Null if the CV "
            "is anonymised or the name can't be confidently identified."
        ),
    )
    current_role: str | None = Field(
        None,
        description=(
            "Most recent / current job title, exactly as the candidate wrote it. "
            "E.g. 'Senior Backend Engineer', 'Frontend Developer', 'Marketing Manager'."
        ),
    )
    skills: list[str] = Field(
        default_factory=list,
        description="Technical skills, frameworks, tools, languages explicitly named in the CV.",
    )
    years_experience: int | None = Field(
        None,
        description="Total years of professional experience. Null if the CV doesn't make it inferable.",
    )
    projects: list[str] = Field(
        default_factory=list,
        description="Notable projects with a one-line description each.",
    )
    domains: list[str] = Field(
        default_factory=list,
        description="Business / industry domains (e.g. fintech, healthcare, e-commerce).",
    )
    education: str | None = Field(
        None,
        description="Highest degree + field, e.g. 'BSc Computer Science' or 'MBA Finance'.",
    )


class JDProfile(BaseModel):
    required_skills: list[str] = Field(
        default_factory=list,
        description="Must-have skills the JD explicitly requires.",
    )
    nice_to_have: list[str] = Field(
        default_factory=list,
        description="Preferred / bonus skills the JD mentions but doesn't require.",
    )
    target_seniority: Literal["junior", "mid", "senior"] = Field(
        ...,
        description="Seniority the role targets. Infer from years required + responsibilities.",
    )
    domain: str | None = Field(
        None,
        description="Primary business domain of the role.",
    )


class ParserOutput(BaseModel):
    """Top-level structured output returned by the parsing agent."""

    cv_profile: CVProfile
    jd_profile: JDProfile
    parse_confidence: float = Field(
        ...,
        description=(
            "Self-assessed parse confidence as a float in [0.0, 1.0]. "
            "Push it down when the CV is ambiguous, sparse, contradictory, or when the JD "
            "is too short to make the required-vs-nice distinction reliably. "
            "Note: range is enforced by the prompt, not by JSON Schema bounds, because "
            "some OpenRouter providers (Bedrock) reject minimum/maximum constraints."
        ),
    )


PARSER_PROMPT = """You parse a candidate CV and a job description into structured JSON.

EXTRACT FROM THE CV (cv_profile):
- candidate_name: full name as it appears at the top of the CV. Null if the
  CV is anonymised or you can't confidently identify a single name.
- current_role: the most recent / current job title from the CV, verbatim
  (e.g. "Senior Backend Engineer", "Frontend Developer").
- skills: every technical skill, framework, tool, or language explicitly named.
  Do NOT invent skills the CV doesn't claim.
- years_experience: total years of professional experience as an integer.
  If unclear, return null.
- projects: 1-line summary of each notable project (max ~8).
- domains: business / industry domains the candidate has worked in.
- education: highest degree + field, e.g. "MSc Computer Science".

EXTRACT FROM THE JD (jd_profile):
- required_skills: skills the JD says the candidate MUST have.
- nice_to_have: skills mentioned as preferred / bonus / a plus.
- target_seniority: one of 'junior', 'mid', 'senior' inferred from required years
  and the scope of responsibilities described.
- domain: the role's primary business domain.

ALSO RETURN parse_confidence (0.0-1.0):
- 0.9+ : both documents are detailed and unambiguous.
- 0.6-0.8 : one of the documents is sparse OR the required-vs-nice distinction is fuzzy.
- <0.6  : significant ambiguity — recruiter should review before the pipeline continues.

Be conservative with confidence — under-claiming is fine, hallucinating is not."""
