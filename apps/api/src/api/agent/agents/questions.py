"""Interview Questions Agent — produces ≥5 questions tailored to the assessment.

Final LLM agent in the pipeline. Skipped via a conditional edge when
``recommendation == "Reject"`` (no point spending tokens generating questions
for a candidate the deterministic scorer just rejected).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class InterviewQuestion(BaseModel):
    area: str = Field(
        ...,
        description=(
            "Short tag describing what the question targets — e.g. "
            "'skill: AWS', 'concern: team-scope', 'strength: scale-experience'. "
            "Each question must tie back to a specific upstream output."
        ),
    )
    question: str = Field(
        ...,
        description="The question itself, written as if you're about to ask it out loud.",
    )
    why_asked: str = Field(
        ...,
        description="One line explaining what signal the interviewer is probing for.",
    )


class QuestionsOutput(BaseModel):
    questions: list[InterviewQuestion] = Field(
        ...,
        description="At least 5 tailored questions.",
    )


QUESTIONS_PROMPT = """You generate interview questions tailored to a specific
candidate-vs-JD assessment. You will receive the parsed profiles plus every
upstream agent's output (matched / missing skills, seniority assessment,
strengths, concerns, integrity flags).

PRODUCE AT LEAST 5 QUESTIONS.

For each question, output:
- area: a short tag tying the question to a specific upstream item.
  Examples: "skill: AWS", "concern: small-team-scope", "strength: payments-domain",
  "gap: education".
- question: the question itself, written exactly as you'd ask it out loud.
- why_asked: ONE line on the signal you're probing for.

DESIRED MIX (aim for this distribution, adapt to what the assessment gave you):
- 1-2 questions VERIFYING a claimed strength — probe depth, not breadth.
- 2-3 questions PROBING a concern, missing skill, or integrity flag.
- 1-2 BEHAVIORAL questions tied to the JD's seniority expectations (ownership,
  cross-team work, mentoring — pick what matches assessed_seniority).

RULES:
- No "tell me about yourself" filler. Every question must trace to a specific
  upstream output.
- No yes/no questions. Force the candidate to give a story or a concrete answer.
- Don't re-ask things the CV already answers (e.g. don't ask 'do you know Python?'
  when Python is in matched_skills).
- If integrity flagged a gap or inconsistency, the question should give the
  candidate a fair chance to explain it — not a 'gotcha'."""
