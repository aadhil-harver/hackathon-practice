"""Integrity & Fairness Agent — surfaces gaps, inconsistencies, and bias flags.

Runs after the parallel assessment fan-out has joined. Writes ``gaps``,
``inconsistencies``, ``bias_flags``, and ``risk_confidence`` to state.
``risk_confidence`` drives confidence gate #2: HIGH means the profile is clean,
LOW means the recruiter should review before scoring continues.

The agent FLAGS — it does not filter, score, or modify the candidate profile.
The recruiter is the final decision-maker on what to do with bias signals.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class IntegrityOutput(BaseModel):
    gaps: list[str] = Field(
        default_factory=list,
        description=(
            "Employment, education, or skill gaps worth surfacing. "
            "Each item must cite a specific CV / profile item, not be a generic concern."
        ),
    )
    inconsistencies: list[str] = Field(
        default_factory=list,
        description=(
            "Self-contradictions in the CV — claims that don't square with other claims. "
            "Only call out genuine contradictions, not 'unusual but plausible' patterns."
        ),
    )
    bias_flags: list[str] = Field(
        default_factory=list,
        description=(
            "Signals that could bias screening if left implicit — e.g. dates that imply age, "
            "names that signal ethnicity, gendered phrasing, gaps the recruiter might "
            "misread. FLAG, do not filter. The recruiter decides what to do."
        ),
    )
    risk_confidence: float = Field(
        ...,
        description=(
            "Float in [0.0, 1.0]. HIGH = profile is clean, low risk; LOW = significant concerns. "
            "Used as the input to confidence gate #2. "
            "Note: range is enforced by the prompt, not by JSON Schema bounds, because some "
            "OpenRouter providers (Bedrock) reject minimum/maximum constraints."
        ),
    )


INTEGRITY_PROMPT = """You inspect a parsed CV + JD and the upstream assessment outputs
for issues a recruiter should see BEFORE the scoring agent runs.

You will receive a JSON payload containing:
  cv_profile, jd_profile, matched_skills, missing_skills,
  assessed_seniority, seniority_evidence, strengths, concerns.

PRODUCE FOUR OUTPUTS:

1. gaps (employment / education / skill gaps):
   - Cite specific items. E.g. "claims 8 years experience but only 5 years of dated
     roles are listed", "no education entry", "missing 3-year window between roles".
   - Skip nice-to-have skill gaps — those belong in missing_skills.

2. inconsistencies (genuine self-contradictions):
   - E.g. claims 'led 10-person team' in one project AND 'sole engineer' in an
     overlapping role at the same company.
   - Do NOT list 'unusual but plausible' patterns as inconsistencies.

3. bias_flags (signals that could bias screening if implicit):
   - E.g. "graduation year reveals age band — flag for recruiter awareness",
     "gendered project descriptors", "career gap with no explanation could be
     misread as commitment issue when parental leave is plausible".
   - FLAG, DO NOT FILTER. Your job is to make these visible, not act on them.
   - Do NOT speculate about protected-class membership the CV doesn't reveal.

4. risk_confidence (0.0-1.0):
   - 0.9+   : clean profile, no concerns.
   - 0.6-0.8: minor flags worth noting but not blocking.
   - <0.6   : significant concerns (multiple inconsistencies, several bias signals,
              or major gaps) — recruiter should review before scoring continues.
   - HIGHER = cleaner / lower-risk. Symmetric with parse_confidence."""
