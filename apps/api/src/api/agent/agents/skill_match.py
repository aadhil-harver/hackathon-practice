"""Skill Match Agent — compares parsed CV skills against parsed JD skills.

Parallel branch #1 of the fan-out. Writes ``matched_skills`` and ``missing_skills``
to state. Does NOT score, assess seniority, or invent skills.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MatchedSkill(BaseModel):
    skill: str = Field(..., description="The skill name, verbatim from the CV.")
    kind: Literal["required", "nice_to_have"] = Field(
        ...,
        description="Whether the JD lists this as required or nice-to-have.",
    )


class SkillMatchOutput(BaseModel):
    matched_skills: list[MatchedSkill] = Field(
        default_factory=list,
        description=(
            "Skills the candidate explicitly has AND the JD asks for "
            "(either as required or nice-to-have)."
        ),
    )
    missing_skills: list[str] = Field(
        default_factory=list,
        description="REQUIRED JD skills the candidate does not have. Don't list nice-to-haves here.",
    )


SKILL_MATCH_PROMPT = """You match skills between a parsed candidate CV and a parsed job description.

You will receive both profiles as JSON. From them:

1. matched_skills: every skill the candidate explicitly has AND the JD asks for.
   - Tag each match as 'required' (in jd_profile.required_skills) or 'nice_to_have'
     (in jd_profile.nice_to_have).
   - Only include skills that appear in cv_profile.skills — do NOT infer skills
     from project descriptions or domain experience. The parser already extracted them.
   - Use fuzzy matching for variants of the same skill (e.g. 'PostgreSQL' vs 'Postgres'),
     but DO NOT match unrelated skills (e.g. 'Python' does not match 'JavaScript').

2. missing_skills: REQUIRED skills (jd_profile.required_skills) the candidate
   does NOT have. Leave nice-to-haves out of this list — only blocking gaps belong here.

Do not score. Do not assess seniority. Do not duplicate the experience agent's
strengths/concerns list. Skill matching is your entire job."""
