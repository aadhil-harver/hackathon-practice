"""Deterministic scoring + recommendation logic.

All pure functions, no LLM calls. Kept in its own module so the graph can stay
focused on orchestration and so the formula is unit-testable in isolation.

The split-into-subscores design is deliberate — every component (skills,
seniority, domain, education) returns a 0-10 score that the recruiter UI
surfaces alongside the final score. Judges can see *why* a score is what it is.
"""

from __future__ import annotations

from typing import Iterable

# Weights from the design diagram. Sum to 1.0 by construction.
WEIGHTS = {
    "skills": 0.40,
    "seniority": 0.30,
    "domain": 0.20,
    "education": 0.10,
}

_SENIORITY_LEVELS = {"junior": 0, "mid": 1, "senior": 2}


def compute_skill_subscore(
    matched_skills: list[dict] | None,
    required_skills: Iterable[str] | None,
    nice_to_have: Iterable[str] | None,
) -> float:
    """0-10 based on required-skill coverage, with nice-to-have as bonus."""
    matched_skills = matched_skills or []
    required = list(required_skills or [])
    nice = list(nice_to_have or [])

    if not required:
        # JD didn't list required skills — give partial credit if there are any matches at all
        return 8.0 if matched_skills else 5.0

    matched_required = sum(1 for m in matched_skills if m.get("kind") == "required")
    coverage = matched_required / len(required)

    matched_nice = sum(1 for m in matched_skills if m.get("kind") == "nice_to_have")
    nice_bonus = min(2.0, matched_nice * 0.5) if nice else 0.0

    return round(min(10.0, coverage * 10.0 + nice_bonus), 2)


def compute_seniority_subscore(assessed: str | None, target: str | None) -> float:
    """0-10 by how well assessed seniority aligns with target seniority."""
    if assessed not in _SENIORITY_LEVELS or target not in _SENIORITY_LEVELS:
        return 5.0

    diff = _SENIORITY_LEVELS[assessed] - _SENIORITY_LEVELS[target]
    if diff == 0:
        return 10.0
    if diff == 1:  # one level over-qualified (e.g. senior for mid role)
        return 7.0
    if diff == -1:  # one level under-qualified
        return 4.0
    if diff > 1:  # very over-qualified — still workable
        return 5.0
    return 1.0  # very under-qualified (e.g. junior for senior role)


def compute_domain_subscore(
    cv_domains: list[str] | None, jd_domain: str | None
) -> float:
    """0-10 by domain overlap. Exact = 10, partial = 5, no overlap = 2."""
    cv_domains = cv_domains or []
    if not jd_domain:
        return 5.0  # JD didn't specify — neutral
    if not cv_domains:
        return 2.0

    jd_lower = jd_domain.lower().strip()
    cv_lower = [d.lower().strip() for d in cv_domains]

    # Exact substring match either direction (fintech vs payments/fintech).
    for d in cv_lower:
        if jd_lower in d or d in jd_lower:
            return 10.0

    # Partial token overlap (excluding short tokens to avoid false positives).
    jd_tokens = {t for t in jd_lower.replace("/", " ").split() if len(t) > 3}
    for d in cv_lower:
        d_tokens = {t for t in d.replace("/", " ").split() if len(t) > 3}
        if jd_tokens & d_tokens:
            return 5.0

    return 2.0


def compute_education_subscore(education: str | None) -> float:
    """0-10 by presence of education entry. Hackathon-simple."""
    if not education:
        return 4.0
    cleaned = education.strip().lower()
    if cleaned in ("", "none", "n/a", "not specified"):
        return 4.0
    return 8.0


def compute_score(
    *,
    matched_skills: list[dict] | None,
    missing_skills: list[str] | None,
    required_skills: Iterable[str] | None,
    nice_to_have: Iterable[str] | None,
    assessed_seniority: str | None,
    target_seniority: str | None,
    cv_domains: list[str] | None,
    jd_domain: str | None,
    education: str | None,
) -> tuple[int, dict]:
    """Apply the weighted formula. Returns ``(score: int 0-10, breakdown: dict)``.

    The breakdown is what the recruiter report UI renders — every subscore is
    exposed so the recruiter can see whether (for example) the score is being
    pulled down by domain mismatch rather than skill gaps.
    """
    skill_subscore = compute_skill_subscore(matched_skills, required_skills, nice_to_have)
    seniority_subscore = compute_seniority_subscore(assessed_seniority, target_seniority)
    domain_subscore = compute_domain_subscore(cv_domains, jd_domain)
    education_subscore = compute_education_subscore(education)

    weighted = (
        WEIGHTS["skills"] * skill_subscore
        + WEIGHTS["seniority"] * seniority_subscore
        + WEIGHTS["domain"] * domain_subscore
        + WEIGHTS["education"] * education_subscore
    )

    final_score = max(0, min(10, round(weighted)))

    breakdown = {
        "skill_subscore": skill_subscore,
        "seniority_subscore": seniority_subscore,
        "domain_subscore": domain_subscore,
        "education_subscore": education_subscore,
        "weights": WEIGHTS,
        "weighted_raw": round(weighted, 2),
    }

    return final_score, breakdown


def score_to_recommendation(score: int) -> str:
    """Deterministic mapping: ``score >= 8 → Shortlist, 5-7 → Hold, <5 → Reject``.

    Lives here (not in the LLM prompt) so the recommendation can never
    contradict the score. This is the contract judges can verify by running
    the same inputs twice.
    """
    if score >= 8:
        return "Shortlist"
    if score >= 5:
        return "Hold"
    return "Reject"