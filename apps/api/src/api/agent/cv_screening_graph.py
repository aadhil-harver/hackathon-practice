"""CV-Screener LangGraph.

Topology (final, matches docs/recruiter_screening.mmd):

    START → input_handler → parser → conf_gate_1
                                       ├─ low conf → human_review_1 → END
                                       └─ pass → [skill_match, seniority, experience]
                                                  └─► integrity → conf_gate_2
                                                                    ├─ high risk → human_review_2 → END
                                                                    └─ pass → scorer → recommendation
                                                                                         ├─ Reject → END
                                                                                         └─ else → interview_questions → END

HITL hard-stop pattern (no Postgres checkpointer — see CLAUDE.md > Non-goals):
- ``conf_gate_1`` / ``conf_gate_2`` are no-op nodes whose only purpose is to
  anchor a conditional edge.
- When confidence is below threshold AND the corresponding ``force_pass_gate_*``
  flag is unset, the conditional edge routes to ``human_review_*``, which writes
  ``review_stage`` to state and ends the graph.
- The Streamlit app captures the terminal state, renders an Approve / Stop panel,
  and on Approve re-invokes ``graph.invoke(...)`` with the snapshot + the
  appropriate ``force_pass_gate_*`` flag set to True.
- To avoid re-paying LLM cost on resume, every LLM-backed node short-circuits
  when its output is already populated in state.
"""

from __future__ import annotations

import json
import logging
import os
import re

from langgraph.graph import END, START, StateGraph

from api.agent.agents.experience import EXPERIENCE_PROMPT, ExperienceOutput
from api.agent.agents.integrity import INTEGRITY_PROMPT, IntegrityOutput
from api.agent.agents.parser import PARSER_PROMPT, ParserOutput
from api.agent.agents.questions import QUESTIONS_PROMPT, QuestionsOutput
from api.agent.agents.seniority import SENIORITY_PROMPT, SeniorityOutput
from api.agent.agents.skill_match import SKILL_MATCH_PROMPT, SkillMatchOutput
from api.agent.llm import make_llm
from api.agent.scoring import compute_score, score_to_recommendation
from api.agent.state import ScreeningState

logger = logging.getLogger(__name__)

# HITL thresholds. Both fields use the convention HIGH = safe, LOW = risky;
# the gate triggers a human review when confidence drops below the threshold.
PARSE_CONFIDENCE_THRESHOLD = 0.6
RISK_CONFIDENCE_THRESHOLD = 0.6

# Floors for the adaptive retry. If OpenRouter reports a budget below the
# floor, we let the error bubble up — there's no point retrying when the
# affordable budget can't fit a reasonable response anyway.
_DEFAULT_RETRY_FLOOR = 200       # parser / skill_match / seniority / experience / integrity
_QUESTIONS_RETRY_FLOOR = 400     # questions agent emits ≥5 structured items

_AFFORD_RE = re.compile(r"can only afford (\d+)")


def _parse_affordable_tokens(message: str) -> int | None:
    """Extract the token budget from an OpenRouter 402 error message."""
    match = _AFFORD_RE.search(message)
    return int(match.group(1)) if match else None


def _profiles_payload(state: ScreeningState) -> str:
    return json.dumps(
        {"cv_profile": state.get("cv_profile"), "jd_profile": state.get("jd_profile")},
        indent=2,
    )


def _full_assessment_payload(state: ScreeningState) -> str:
    return json.dumps(
        {
            "cv_profile": state.get("cv_profile"),
            "jd_profile": state.get("jd_profile"),
            "matched_skills": state.get("matched_skills"),
            "missing_skills": state.get("missing_skills"),
            "assessed_seniority": state.get("assessed_seniority"),
            "seniority_evidence": state.get("seniority_evidence"),
            "strengths": state.get("strengths"),
            "concerns": state.get("concerns"),
            "gaps": state.get("gaps"),
            "inconsistencies": state.get("inconsistencies"),
            "bias_flags": state.get("bias_flags"),
            "score": state.get("score"),
            "score_breakdown": state.get("score_breakdown"),
            "recommendation": state.get("recommendation"),
        },
        indent=2,
        default=str,
    )


def build_screening_graph():
    """Build and compile the CV-Screener StateGraph."""
    # Initial preferred budgets. Each LLM node will retry at a smaller budget
    # if OpenRouter reports a lower per-request affordability at runtime — see
    # ``_invoke_with_retry`` below.
    extraction_budget = int(os.getenv("INTERVIEW_MAX_TOKENS", "800"))
    questions_budget = int(os.getenv("QUESTIONS_MAX_TOKENS", "1200"))

    def _invoke_with_retry(
        *,
        temperature: float,
        max_tokens: int,
        output_schema,
        messages,
        floor: int = _DEFAULT_RETRY_FLOOR,
    ):
        """Invoke a structured-output LLM with adaptive max_tokens on 402.

        Low-credit OpenRouter accounts have a per-request cap that fluctuates
        between runs. The error message tells us exactly what the account can
        afford — we parse that, rebuild the LLM at ``affordable - 30`` for
        a small safety margin, and retry once. Anything that's not a 402, or
        a 402 with an affordable budget below ``floor``, propagates up.
        """
        budget = max_tokens
        for attempt in (1, 2):
            try:
                llm = make_llm(
                    temperature=temperature, max_tokens=budget
                ).with_structured_output(output_schema)
                return llm.invoke(messages)
            except Exception as exc:  # noqa: BLE001 — narrow check below
                msg = str(exc)
                if "402" not in msg or attempt == 2:
                    raise
                affordable = _parse_affordable_tokens(msg)
                if not affordable or affordable < floor:
                    raise
                budget = max(floor, affordable - 30)
                logger.warning(
                    "LLM retrying with max_tokens=%d (OpenRouter affordable=%d, was %d)",
                    budget,
                    affordable,
                    max_tokens,
                )
        raise RuntimeError("retry loop exited unexpectedly")

    # ── Node functions ───────────────────────────────────────────────────

    def input_handler(state: ScreeningState):
        cv_text = (state.get("cv_text") or "").strip()
        jd_text = (state.get("jd_text") or "").strip()
        if not cv_text or not jd_text:
            raise ValueError("Both cv_text and jd_text must be provided.")
        return {"cv_text": cv_text, "jd_text": jd_text}

    def parser(state: ScreeningState):
        # Skip-if-cached: on HITL resume, the prior parse is already in state.
        # Re-running it would waste tokens AND could land a slightly different
        # confidence value, bypassing the force_pass intent.
        if state.get("cv_profile") is not None:
            return {}
        result: ParserOutput = _invoke_with_retry(
            temperature=0.1,
            max_tokens=extraction_budget,
            output_schema=ParserOutput,
            messages=[
                {"role": "system", "content": PARSER_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"CV:\n{state['cv_text']}\n\n"
                        f"---\n\n"
                        f"JOB DESCRIPTION:\n{state['jd_text']}"
                    ),
                },
            ],
        )
        return {
            "cv_profile": result.cv_profile.model_dump(),
            "jd_profile": result.jd_profile.model_dump(),
            "parse_confidence": result.parse_confidence,
        }

    def conf_gate_1(state: ScreeningState):
        """Anchor node for the conditional edge — no state mutation."""
        return {}

    def _route_after_gate_1(state: ScreeningState):
        # Recruiter approval bypasses the threshold check.
        if state.get("force_pass_gate_1"):
            return ["skill_match", "seniority", "experience"]
        confidence = state.get("parse_confidence") or 0.0
        if confidence < PARSE_CONFIDENCE_THRESHOLD:
            return "human_review_1"
        return ["skill_match", "seniority", "experience"]

    def human_review_1(state: ScreeningState):
        """Terminal sink for gate #1. Streamlit reads ``review_stage`` to detect this."""
        return {"review_stage": "gate_1"}

    def skill_match(state: ScreeningState):
        if state.get("matched_skills") is not None:
            return {}
        result: SkillMatchOutput = _invoke_with_retry(
            temperature=0.1,
            max_tokens=extraction_budget,
            output_schema=SkillMatchOutput,
            messages=[
                {"role": "system", "content": SKILL_MATCH_PROMPT},
                {"role": "user", "content": _profiles_payload(state)},
            ],
        )
        return {
            "matched_skills": [m.model_dump() for m in result.matched_skills],
            "missing_skills": result.missing_skills,
        }

    def seniority(state: ScreeningState):
        if state.get("assessed_seniority") is not None:
            return {}
        result: SeniorityOutput = _invoke_with_retry(
            temperature=0.1,
            max_tokens=extraction_budget,
            output_schema=SeniorityOutput,
            messages=[
                {"role": "system", "content": SENIORITY_PROMPT},
                {"role": "user", "content": _profiles_payload(state)},
            ],
        )
        return {
            "assessed_seniority": result.assessed_seniority,
            "seniority_evidence": result.seniority_evidence,
        }

    def experience(state: ScreeningState):
        if state.get("strengths") is not None:
            return {}
        result: ExperienceOutput = _invoke_with_retry(
            temperature=0.1,
            max_tokens=extraction_budget,
            output_schema=ExperienceOutput,
            messages=[
                {"role": "system", "content": EXPERIENCE_PROMPT},
                {"role": "user", "content": _profiles_payload(state)},
            ],
        )
        return {"strengths": result.strengths, "concerns": result.concerns}

    def integrity(state: ScreeningState):
        if state.get("risk_confidence") is not None:
            return {}
        result: IntegrityOutput = _invoke_with_retry(
            temperature=0.1,
            max_tokens=extraction_budget,
            output_schema=IntegrityOutput,
            messages=[
                {"role": "system", "content": INTEGRITY_PROMPT},
                {"role": "user", "content": _full_assessment_payload(state)},
            ],
        )
        return {
            "gaps": result.gaps,
            "inconsistencies": result.inconsistencies,
            "bias_flags": result.bias_flags,
            "risk_confidence": result.risk_confidence,
        }

    def conf_gate_2(state: ScreeningState):
        return {}

    def _route_after_gate_2(state: ScreeningState):
        if state.get("force_pass_gate_2"):
            return "scorer"
        confidence = state.get("risk_confidence") or 0.0
        if confidence < RISK_CONFIDENCE_THRESHOLD:
            return "human_review_2"
        return "scorer"

    def human_review_2(state: ScreeningState):
        return {"review_stage": "gate_2"}

    def scorer(state: ScreeningState):
        cv_profile = state.get("cv_profile") or {}
        jd_profile = state.get("jd_profile") or {}
        score, breakdown = compute_score(
            matched_skills=state.get("matched_skills"),
            missing_skills=state.get("missing_skills"),
            required_skills=jd_profile.get("required_skills"),
            nice_to_have=jd_profile.get("nice_to_have"),
            assessed_seniority=state.get("assessed_seniority"),
            target_seniority=jd_profile.get("target_seniority"),
            cv_domains=cv_profile.get("domains"),
            jd_domain=jd_profile.get("domain"),
            education=cv_profile.get("education"),
        )
        return {"score": score, "score_breakdown": breakdown}

    def recommendation(state: ScreeningState):
        score = state.get("score")
        if score is None:
            raise RuntimeError("recommendation node ran before scorer populated 'score'")
        return {"recommendation": score_to_recommendation(score)}

    def interview_questions(state: ScreeningState):
        """Generate ≥5 questions, with a higher retry floor than other nodes."""
        if state.get("questions") is not None:
            return {}
        result: QuestionsOutput = _invoke_with_retry(
            temperature=0.3,
            max_tokens=questions_budget,
            output_schema=QuestionsOutput,
            messages=[
                {"role": "system", "content": QUESTIONS_PROMPT},
                {"role": "user", "content": _full_assessment_payload(state)},
            ],
            floor=_QUESTIONS_RETRY_FLOOR,
        )
        return {"questions": [q.model_dump() for q in result.questions]}

    def _skip_on_reject(state: ScreeningState):
        if state.get("recommendation") == "Reject":
            return "end"
        return "interview_questions"

    # ── Graph assembly ───────────────────────────────────────────────────

    builder = StateGraph(ScreeningState)

    builder.add_node("input_handler", input_handler)
    builder.add_node("parser", parser)
    builder.add_node("conf_gate_1", conf_gate_1)
    builder.add_node("human_review_1", human_review_1)
    builder.add_node("skill_match", skill_match)
    builder.add_node("seniority", seniority)
    builder.add_node("experience", experience)
    builder.add_node("integrity", integrity)
    builder.add_node("conf_gate_2", conf_gate_2)
    builder.add_node("human_review_2", human_review_2)
    builder.add_node("scorer", scorer)
    builder.add_node("recommendation", recommendation)
    builder.add_node("interview_questions", interview_questions)

    builder.add_edge(START, "input_handler")
    builder.add_edge("input_handler", "parser")
    builder.add_edge("parser", "conf_gate_1")

    # Gate #1 fans out OR routes to human_review_1.
    builder.add_conditional_edges(
        "conf_gate_1",
        _route_after_gate_1,
        path_map=["skill_match", "seniority", "experience", "human_review_1"],
    )
    builder.add_edge("human_review_1", END)

    # Join: integrity fires only after all three parallel branches return.
    builder.add_edge("skill_match", "integrity")
    builder.add_edge("seniority", "integrity")
    builder.add_edge("experience", "integrity")

    builder.add_edge("integrity", "conf_gate_2")
    builder.add_conditional_edges(
        "conf_gate_2",
        _route_after_gate_2,
        path_map=["scorer", "human_review_2"],
    )
    builder.add_edge("human_review_2", END)

    builder.add_edge("scorer", "recommendation")
    builder.add_conditional_edges(
        "recommendation",
        _skip_on_reject,
        {"interview_questions": "interview_questions", "end": END},
    )
    builder.add_edge("interview_questions", END)

    return builder.compile()


# Module-level compiled graph for callers (FastAPI lifespan, Streamlit).
screening_graph = build_screening_graph()
