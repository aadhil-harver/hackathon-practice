"""Golden-path demo scenarios — the live-demo script in code form.

Each scenario pairs one of the sample CVs with the senior-backend JD and
records the expected score band + recommendation per the rubric in CLAUDE.md.
The Streamlit UI loads these from a dropdown so judges can replay any branch
of the decision tree.
"""

from __future__ import annotations

from dataclasses import dataclass

from api.agent.data.sample_cvs import (
    MARKETING_MANAGER_CV,
    MID_FRONTEND_CV,
    SENIOR_PYTHON_AWS_CV,
)
from api.agent.data.sample_jds import SENIOR_BACKEND_FINTECH_JD


@dataclass(frozen=True)
class GoldenPath:
    """One end-to-end demo scenario."""

    key: str  # short id used in the UI dropdown
    label: str  # human-friendly title
    description: str  # one-line summary of what this scenario proves
    cv: str
    jd: str
    expected_band: str  # "8-10" / "5-7" / "<5"
    expected_recommendation: str  # "Shortlist" / "Hold" / "Reject"


GOLDEN_PATHS: list[GoldenPath] = [
    GoldenPath(
        key="shortlist",
        label="1 · Senior Python/AWS engineer → Shortlist",
        description=(
            "Happy path. 8-year senior, fintech domain match, all required skills "
            "covered, mentoring signal present. Expected score 8-10."
        ),
        cv=SENIOR_PYTHON_AWS_CV,
        jd=SENIOR_BACKEND_FINTECH_JD,
        expected_band="8-10",
        expected_recommendation="Shortlist",
    ),
    GoldenPath(
        key="hold",
        label="2 · 2-yr frontend dev → Hold",
        description=(
            "Borderline path. Frontend background, some Python exposure, missing "
            "AWS / Postgres / scale experience. Expected score 5-7."
        ),
        cv=MID_FRONTEND_CV,
        jd=SENIOR_BACKEND_FINTECH_JD,
        expected_band="5-7",
        expected_recommendation="Hold",
    ),
    GoldenPath(
        key="reject",
        label="3 · Marketing manager → Reject",
        description=(
            "Negative path. No engineering skills, wrong domain. Recommendation "
            "drops to Reject — interview questions are skipped. Expected score < 5."
        ),
        cv=MARKETING_MANAGER_CV,
        jd=SENIOR_BACKEND_FINTECH_JD,
        expected_band="<5",
        expected_recommendation="Reject",
    ),
]


def by_key(key: str) -> GoldenPath:
    """Lookup helper used by the Streamlit dropdown."""
    for gp in GOLDEN_PATHS:
        if gp.key == key:
            return gp
    raise KeyError(f"Unknown golden-path key: {key!r}")
