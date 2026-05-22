# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Hackathon scoring criteria

This repo is for the Gapstars AI Hackathon (May 22). Guiding principle: **a working demo beats a polished idea every time.** Optimize work toward these weighted criteria:

| Weight | Criterion | What judges look for |
| --- | --- | --- |
| 30% | Correctness | Does the workflow actually work? |
| 25% | Agent Design Quality | Are the agent roles clearly defined? |
| 20% | Execution & Demo | Can you show it running live? |
| 15% | Technical Depth | How well is the system architected? |
| 10% | UX / Experience | Is it easy to follow? |

When making trade-offs, prefer a runnable end-to-end flow with well-scoped agent roles over breadth, polish, or speculative features.

## Problem statement

A recruiter or technical interviewer at a mid-sized tech company opens our tool when a fresh CV lands against an open role. Today they spend 15–30 minutes per CV skimming for relevant skills, second-guessing seniority, mentally matching against the JD, then context-switching again to draft interview questions — and they do this dozens of times a week, so the later CVs get rushed and inconsistent. **CV-Screener takes a candidate CV and a job description and returns a structured hiring recommendation in under a minute**: a candidate summary, matched/missing skills, strengths and concerns, a score out of 10, a deterministic Shortlist / Hold / Reject call, and at least 5 tailored interview questions. Success = the recruiter can act on the output without re-reading the CV, and a second run on the same inputs produces a consistent recommendation. We use multiple agents (not one prompt) because *analysis*, *scoring*, and *question generation* are distinct judgment calls — separating them makes each step inspectable and the final recommendation defensible.

## Golden-path scenarios (demo + regression targets)

Three cases that exercise every decision branch. These double as the live-demo script.

| # | Input (CV + JD) | Expected score band | Expected recommendation | What it proves |
| --- | --- | --- | --- | --- |
| 1 | Senior Python/AWS engineer CV vs. Senior Backend Engineer JD | 8–10 | **Shortlist** | Happy path — analyzer extracts seniority correctly, scorer rewards strong matches, questions probe depth not basics |
| 2 | 2-yr frontend dev CV vs. Senior Backend Engineer JD | 5–7 | **Hold** | Borderline path — `missing_skills` is non-empty, reasoning names the gap, questions target the gap areas |
| 3 | Marketing manager CV vs. Senior Backend Engineer JD | <5 | **Reject** | Negative path — system doesn't hallucinate matched skills, reasoning is honest, question-generation is skipped (or returns a "not recommended" note) |

**Per-case acceptance check:** output contains the 7 required fields (summary, matched skills, missing skills, strengths, concerns, score, recommendation, questions); recommendation matches the score band per the rubric; reasoning cites at least one specific item from the CV.

## Agent role contracts

| Agent | Purpose | Input | Output | Must NOT do | Hands off when |
| --- | --- | --- | --- | --- | --- |
| **CV Analyzer** | Extract a structured candidate profile from raw CV text | Raw CV text | `{skills[], years_experience, projects[], seniority, domains[]}` | Compare to JD, score, or recommend — analysis only | Profile object is populated |
| **Fit Scorer** | Compare profile against JD and produce a defensible recommendation | Analyzer output + JD (+ optional must-have / nice-to-have skills, seniority) | `{matched_skills[], missing_skills[], strengths[], concerns[], score:int(0-10), recommendation, reasoning}` | Generate interview questions; invent skills not present in the CV; pick a recommendation that contradicts the score band | Score and recommendation are set |
| **Interview Question Generator** *(optional per brief, kept in for demo)* | Produce ≥5 role-specific questions targeting strengths to verify and gaps to probe | Analyzer output + Scorer output | `questions: [{area, question, why_asked}]` (≥5) | Re-score, change the recommendation, or ask generic "tell me about yourself" filler | 5+ questions exist, each tagged to a strength or concern |

**Decision logic (enforced in code, not the LLM):**
`score >= 8 → Shortlist`, `5 <= score <= 7 → Hold`, `score < 5 → Reject`.
The LLM proposes a score; the score→recommendation mapping is deterministic Python. Judges can trust that the recommendation can never contradict the score.

**Orchestration:** `CV Analyzer → Fit Scorer → Interview Question Generator`. Question generation is skipped when `recommendation == "Reject"` (saves tokens, matches real recruiter behavior).

## Acceptance criteria (judge-visible checklist)

Demo is "done" when **all** of these are demonstrably true on stage:

- [ ] User submits a CV and a job description through the UI.
- [ ] System returns a **structured** evaluation (not free-form prose).
- [ ] Output includes a **score (0–10)** and a **recommendation** (Shortlist / Hold / Reject).
- [ ] Output includes **reasoning** that cites specific CV evidence.
- [ ] System generates **≥5 interview questions** (except on Reject).
- [ ] **≥2 agents are clearly involved** and visible in the run — agent boundaries shown in the UI, logs, or trace panel.

## Non-goals (explicit scope discipline)

Out of scope for the hackathon demo — listed so we don't accidentally build them and dilute Correctness:

- Recruiter-friendly polished summary export, technical-interviewer briefing note, technical-vs-communication split scoring, PDF/email export *(brief's "Stretch Ideas" — pursue only after acceptance criteria are green and the demo runs end-to-end).*
- Multi-CV batch screening, ATS integration, candidate-facing UI, authentication, persistence across sessions.
- Fine-tuning, custom embeddings, RAG over a JD corpus — single-shot LLM calls per agent are enough.

## Common commands

Dependencies are managed with `uv` (see `.python-version` for the pinned Python). All runtime commands go through `uv run`:

```bash
uv sync                                       # install deps into .venv
uv run streamlit run interview_app.py         # Streamlit UI (default port 8501) — current boilerplate
uv run python interview.py                    # CLI routed interview-prep bot (type "exit" to quit)
```

An `OPENROUTER_API_KEY` in `.env` at the repo root is required — `interview.py` points `ChatOpenAI` at the OpenRouter base URL. The model defaults to `anthropic/claude-sonnet-4.6` and can be overridden with `INTERVIEW_MODEL`; `INTERVIEW_MAX_TOKENS` caps output (default 800) because OpenRouter rejects oversized `max_tokens` on low-credit accounts.

Optional LangSmith tracing: set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in `.env`. The project name defaults to `interview-prep` (override via `LANGSMITH_PROJECT`); each turn is grouped under a `interview-turn` parent run with `surface` and `turn` metadata.

`main.py` / `simple.py` / `app.py` are legacy therapy-vs-logical demos kept only for reference — they require `GROQ_API_KEY` and are not the boilerplate being extended.

There is no test suite, linter, or formatter configured.

## Architecture (current boilerplate — to be repurposed for CV-Screener)

The active entry points are `interview.py` (graph + CLI) and `interview_app.py` (Streamlit UI). Both share one compiled `graph`.

**`interview.py` owns the graph.** A six-node `StateGraph`:

```
START → classifier → router → (technical | behavioral | hr_career) → coach → END
```

- `InterviewState` is a `TypedDict` with `messages` (`add_messages` reducer, appends), `question_type: str | None`, and `coach_tips: str | None`.
- `classify_question` uses `llm.with_structured_output(QuestionClassifier)` — a Pydantic model with `Literal["technical", "behavioral", "hr_career"]` — to force a typed bucket. The classifier prompt explicitly handles **follow-up turns**: short refinements ("make it shorter", "for a junior role") inherit the prior bucket instead of being reclassified on the fragment alone.
- `router` is a node that returns `{"next": question_type}`; the actual branching is a `conditional_edges` call reading `state["next"]`. As before, `next` lives in state but is not declared in the `InterviewState` TypedDict.
- Each specialist (`technical_agent`, `behavioral_agent`, `hr_career_agent`) receives the **full conversation history** via `_history_as_dicts(state["messages"])`, so role/seniority clarifications carry across turns. Each appends a single assistant message to `messages`.
- `coach_agent` runs unconditionally after every specialist, reads the latest user question + the specialist's reply, and writes a short delivery-tips string into `state["coach_tips"]` (it does **not** append to `messages`, so it stays out of the next turn's classifier input).

**`interview_app.py` wraps the same graph.** It imports `graph` from `interview` and uses `graph.stream(...)` to surface each node inside a `st.status` panel. Unlike the legacy `app.py`, it **does** maintain multi-turn context: it rebuilds the full chat history from `st.session_state.messages` and feeds it into `graph_input["messages"]` every turn. Coach tips are stored on the assistant message under a separate `coach` key and are intentionally **not** re-fed into the graph (they'd pollute the classifier). Each turn is wrapped in a LangSmith `RunnableConfig` with `run_name="interview-turn"` and `surface`/`turn` metadata.

## Things to watch for when changing this code

- `interview_app.py` depends on the exact node names (`classifier`, `router`, `technical`, `behavioral`, `hr_career`, `coach`) emitted by `graph.stream` to render status updates. Renaming a node in `interview.py` will silently break the status panel.
- The classifier's `Literal` values and the router's conditional-edge mapping must stay in sync with `interview_app.py`'s `AGENT_BADGE` dict. Adding a fourth specialist means updating all three places.
- Coach tips are written to `state["coach_tips"]` and rendered separately in the UI; they are **not** appended to `messages`. If you start appending them, the next turn's classifier will see coaching prose as conversational context and may misclassify follow-ups.
- `_history_as_dicts` maps LangChain message `type` to OpenAI-style `role` (`"human" → "user"`, everything else → `"assistant"`). If a system message ever lands in `state["messages"]`, it will be tagged as assistant — keep system prompts out of state and pass them only at invocation time.
- OpenRouter enforces a `max_tokens` upper bound against remaining credit. The explicit `max_tokens` arg on `ChatOpenAI` is load-bearing; removing it sends `max_tokens=65536` and low-credit accounts will get rejected.

## Using this as the CV-Screener boilerplate

When pivoting to the problem statement above, the interview-prep graph is the template — same shape, different agents:

- `classifier` / `router` are not needed (CV-Screener has a fixed pipeline, not a branch). Replace with a linear `START → analyzer → scorer → questions → END`.
- `coach_agent` is the closest analogue to the **Interview Question Generator** — a downstream agent that reads upstream state and writes to its own state key without mutating `messages`. Mirror that pattern.
- The deterministic `score → recommendation` mapping (see Agent role contracts) should live as plain Python inside or after the `scorer` node, **not** as an LLM instruction.
- Keep the `graph.stream(...)` + `st.status` pattern from `interview_app.py` — judges' acceptance criterion "≥2 agents clearly involved and visible in the run" is satisfied by exactly this panel.
- Keep the LangSmith `RunnableConfig` wrapping per turn so demo runs are inspectable; rename `run_name` to something like `cv-screening-run`.
