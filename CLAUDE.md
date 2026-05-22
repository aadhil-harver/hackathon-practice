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

A recruiter or technical interviewer at a mid-sized tech company opens our tool when a fresh CV lands against an open role. Today they spend 15–30 minutes per CV skimming for relevant skills, second-guessing seniority, mentally matching against the JD, then context-switching again to draft interview questions — and they do this dozens of times a week, so the later CVs get rushed and inconsistent. **CV-Screener takes a candidate CV and a job description and returns a structured hiring recommendation in under a minute**: matched/missing skills, an assessed seniority band, strengths and concerns, integrity/fairness flags, a weighted score out of 10, a deterministic Shortlist / Hold / Reject call, and at least 5 tailored interview questions. Success = the recruiter can act on the output without re-reading the CV, and a second run on the same inputs produces a consistent recommendation. We use a **multi-agent graph** (not one prompt) because *parsing*, *skill/seniority/experience assessment*, *integrity & fairness*, *scoring*, and *question generation* are distinct judgment calls — separating them makes each step inspectable, lets us run the assessment agents in parallel, and inserts two **human-in-the-loop confidence gates** (after parsing and after the integrity check) where the recruiter is asked to approve before the pipeline continues. The final score → recommendation mapping is deterministic Python so the call can never contradict the score the LLM proposed.

## Golden-path scenarios (demo + regression targets)

Three cases that exercise every decision branch. These double as the live-demo script.

| # | Input (CV + JD) | Expected score band | Expected recommendation | What it proves |
| --- | --- | --- | --- | --- |
| 1 | Senior Python/AWS engineer CV vs. Senior Backend Engineer JD | 8–10 | **Shortlist** | Happy path — analyzer extracts seniority correctly, scorer rewards strong matches, questions probe depth not basics |
| 2 | 2-yr frontend dev CV vs. Senior Backend Engineer JD | 5–7 | **Hold** | Borderline path — `missing_skills` is non-empty, reasoning names the gap, questions target the gap areas |
| 3 | Marketing manager CV vs. Senior Backend Engineer JD | <5 | **Reject** | Negative path — system doesn't hallucinate matched skills, reasoning is honest, question-generation is skipped (or returns a "not recommended" note) |

**Per-case acceptance check:** output contains the 7 required fields (summary, matched skills, missing skills, strengths, concerns, score, recommendation, questions); recommendation matches the score band per the rubric; reasoning cites at least one specific item from the CV.

## Agent role contracts

The pipeline has **8 functional agents + 2 HITL gates**. Visualised as a mermaid flowchart it's a vertical pipeline with a 3-way parallel fan-out in the middle. Source-of-truth diagram: `docs/recruiter_screening.mmd` (the mermaid code the design was approved against).

```
START → input_handler → parser → conf_gate_1
                                   ├─ low_conf → END (HITL: needs review)
                                   └─ pass → ┬── skill_match ──┐
                                             ├── seniority ────┼──► integrity → conf_gate_2
                                             └── experience ───┘                  ├─ high_risk → END (HITL: needs review)
                                                                                  └─ pass → scorer → recommendation
                                                                                                      ├─ Reject → END
                                                                                                      └─ else → questions → END
```

| # | Agent | Type | Input | Output (state keys it writes) | Must NOT do |
| --- | --- | --- | --- | --- | --- |
| 0 | **Input Handler** | Entry node | Raw CV file/text + JD file/text | `cv_text`, `jd_text` | LLM work; just normalises text |
| 1 | **Parsing Agent** | LLM | `cv_text`, `jd_text` | `cv_profile = {skills[], years_experience, projects[], domains[], education}`, `jd_profile = {required_skills[], nice_to_have[], target_seniority, domain}`, `parse_confidence: float` | Compare or score — extraction only |
| — | **Confidence Gate #1** | Conditional edge (HITL) | `parse_confidence` | Routes to `human_review_1` (END) when conf < threshold, else to fan-out | Auto-bypass the gate — recruiter must Approve in UI |
| 2 | **Skill Match** | LLM (parallel) | `cv_profile`, `jd_profile` | `matched_skills[]`, `missing_skills[]` | Score, assess seniority, or invent skills not in CV |
| 3 | **Seniority** | LLM (parallel) | `cv_profile`, `jd_profile` | `assessed_seniority: "junior"|"mid"|"senior"`, `seniority_evidence` | Score or recommend |
| 4 | **Experience** | LLM (parallel) | `cv_profile`, `jd_profile` | `strengths[]`, `concerns[]` | Score, recommend, or duplicate skill matching |
| 5 | **Integrity & Fairness** | LLM | all upstream outputs | `gaps[]`, `inconsistencies[]`, `bias_flags[]`, `risk_confidence: float` | Score, modify the candidate profile, or block solely on protected-class signals (it flags, the recruiter decides) |
| — | **Confidence Gate #2** | Conditional edge (HITL) | `risk_confidence` + `bias_flags` count | Routes to `human_review_2` (END) when high-risk, else to scorer | Auto-bypass — recruiter must Approve |
| 6 | **Scoring Agent** | **Deterministic Python** | matched/missing skills, assessed seniority, domain match, education | `score: int(0–10)` via weighted formula: `0.4·skills + 0.3·seniority + 0.2·domain + 0.1·edu` | Call the LLM; produce a recommendation; deviate from the weighting without explicit recruiter override |
| — | *Human Override* | *(skipped in v1 — see Non-goals)* | — | — | — |
| 7 | **Recommendation** | **Deterministic Python** | `score` | `recommendation: "Shortlist"|"Hold"|"Reject"` via `>=8 / 5-7 / <5` | Reason about the candidate — pure mapping |
| 8 | **Interview Questions** | LLM (conditional) | all upstream outputs | `questions: [{area, question, why_asked}]` (≥5) — **skipped if recommendation == "Reject"** | Re-score, change recommendation, or ask generic "tell me about yourself" filler |
| 9 | *Recruiter Report* | Streamlit view | full state | Renders score breakdown, flags, questions | Not a graph node; pure presentation |

**Decision logic (enforced in code, not the LLM):**
`score >= 8 → Shortlist`, `5 <= score <= 7 → Hold`, `score < 5 → Reject`. The LLM never proposes the recommendation; the scorer's integer goes through pure Python. Judges can trust the recommendation can never contradict the score.

**HITL hard-stop pattern (v1 implementation):** the two confidence gates terminate the graph early at a `human_review_*` sink node. The Streamlit app inspects the terminal state, renders the partial output plus an **Approve / Override** panel, and on Approve, calls `graph.invoke()` a second time with the gate's `pass` branch forced (by setting a `force_pass_gate_n` flag in the input state). No Postgres checkpointer — the paused state lives in `st.session_state` between clicks. The `human_override` node from the original diagram is deferred to v2.

**Parallel fan-out:** `skill_match`, `seniority`, and `experience` all receive an edge from the `conf_gate_1.pass` branch. Each writes to disjoint state keys so the `add_messages`-style reducer never has to merge conflicting updates. The `integrity` node is the join point — LangGraph only fires it once all three parallel branches have returned.

## Acceptance criteria (judge-visible checklist)

Demo is "done" when **all** of these are demonstrably true on stage:

- [ ] User submits a CV and a job description through the UI.
- [ ] System returns a **structured** evaluation (not free-form prose).
- [ ] Output includes a **score (0–10)** and a **recommendation** (Shortlist / Hold / Reject).
- [ ] Score is produced by a **deterministic weighted formula** (40/30/20/10), not by the LLM directly.
- [ ] Output includes **reasoning** that cites specific CV evidence (strengths/concerns name items from the parsed profile).
- [ ] **Integrity & Fairness flags** are surfaced (gaps, inconsistencies, bias signals).
- [ ] System generates **≥5 interview questions** (except on Reject).
- [ ] **≥2 agents are clearly involved** and visible in the run — agent boundaries shown in the UI, logs, or trace panel. (We have 8, the parallel fan-out is the headline.)
- [ ] **HITL gates trigger and resolve correctly**: at least one golden-path scenario fires a confidence gate, and the Approve button resumes the pipeline to completion.

## Non-goals (explicit scope discipline)

Out of scope for the hackathon demo — listed so we don't accidentally build them and dilute Correctness:

- **Human Override node** (mid-pipeline weight adjustment) — deferred to v2. v1 hard-codes the 40/30/20/10 weights. If we add it back, the cleanest place is between `scorer` and `recommendation`, as a Streamlit panel that lets the recruiter bump the integer score.
- **Real LangGraph `interrupt_before` + Postgres checkpointer** — we use a lighter "hard-stop + force_pass flag" pattern (see Agent role contracts) so persistence stays out of scope and the demo runs purely in-memory.
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

When pivoting to the problem statement above, the interview-prep graph at `apps/api/src/api/agent/graph.py` is the template — same file layout, different topology:

- `classifier` / `router` go away. The CV-Screener pipeline has a fixed shape (see Agent role contracts) — not a content-based branch.
- The three parallel specialists (`technical` / `behavioral` / `hr_career`) become the three parallel **assessment** agents (`skill_match` / `seniority` / `experience`). Same `add_node` + multi-edge fan-out pattern — just three edges out of `conf_gate_1.pass` instead of a conditional edge picking one specialist.
- `coach_agent` is the closest analogue to the **Interview Questions** agent — both read upstream state and write to a separate state key without mutating `messages`. Mirror that. Add a conditional edge **before** it that routes to END when `recommendation == "Reject"`.
- The deterministic `score → recommendation` mapping (see Agent role contracts) should live as plain Python inside or after the `scorer` node, **not** as an LLM instruction. Same goes for the weighted-score formula in `scorer`.
- HITL gates use the same `add_conditional_edges` pattern as the existing `router` node — the only twist is that one branch ends at a `human_review_*` sink node which the Streamlit app inspects and resumes from. See "HITL hard-stop pattern" under Agent role contracts.
- Keep the `graph.stream(...)` + `st.status` pattern from `apps/web/streamlit_app.py` — judges' acceptance criterion "≥2 agents clearly involved and visible in the run" is satisfied by exactly this panel. The fan-out makes it more visually impressive (three agents firing in parallel).
- Keep the LangSmith `RunnableConfig` wrapping per turn so demo runs are inspectable; rename `run_name` from `interview-turn` to `cv-screening-run`.

## Target project structure (CV-Screener build plan)

Reference: `customer-support-multi-agent-platform` (FastAPI + LangGraph monorepo). We mirror its layout so the move from "single Streamlit script" → "structured demo" is mechanical, not a rewrite. Adapt — do not copy verbatim — and keep the Streamlit UI as the primary surface; the FastAPI app is optional but unlocks the `/api/chat/stream` SSE pattern judges find easier to read than `st.status`.

```
hackathon-practice/
├── apps/
│   ├── api/                              # FastAPI + LangGraph backend (optional but recommended)
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   ├── uv.lock
│   │   └── src/api/
│   │       ├── __init__.py
│   │       ├── main.py                   # FastAPI app factory + lifespan + CORS
│   │       ├── config.py                 # pydantic-settings Settings class
│   │       ├── cli.py                    # Typer CLI (`api dev`, `api serve`)
│   │       ├── agent/
│   │       │   ├── __init__.py
│   │       │   ├── graph.py              # build_graph() → compiled StateGraph
│   │       │   ├── state.py              # ScreeningState TypedDict
│   │       │   ├── agents/               # System prompts per agent
│   │       │   │   ├── analyzer.py
│   │       │   │   ├── scorer.py
│   │       │   │   └── questions.py
│   │       │   └── data/                 # Sample CVs + JDs for the 3 golden-path scenarios
│   │       │       ├── sample_cvs.py
│   │       │       └── sample_jds.py
│   │       └── routers/
│   │           ├── __init__.py
│   │           └── screen.py             # POST /api/screen, POST /api/screen/stream
│   └── web/                              # Streamlit UI (keep) OR Next.js (stretch)
│       └── streamlit_app.py              # current interview_app.py, repurposed
├── packages/                             # Shared schemas (future use)
├── docker-compose.yml
├── .env.example
├── CLAUDE.md
└── README.md
```

**Migration hint:** the current `interview.py` collapses graph + agents + CLI into one file. The reference splits them into `agent/graph.py`, `agent/agents/*.py` (prompts only), `agent/state.py`, and `cli.py`. Do this split as the *first* refactor so each agent's prompt is its own diff and adding the third agent doesn't conflict.

## FastAPI + LangGraph setup (from reference)

Anchor patterns to lift wholesale. Each one solves a specific demo problem.

**1. App factory + lifespan** (`apps/api/src/api/main.py`) — build the graph once at startup, hang it on `app.state.graph`, close any pools at shutdown:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.graph = build_graph()        # add checkpointer arg if persistence is in scope
    yield
    # pool.close() etc.

def create_app() -> FastAPI:
    app = FastAPI(title="CV-Screener API", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins_list, ...)
    app.include_router(screen_router)
    @app.get("/api/health")
    async def health(): return {"status": "ok"}
    return app

app = create_app()
```

**2. Settings via pydantic-settings** (`config.py`) — `BaseSettings` with `env_file=".env"`, an `@lru_cache` `get_settings()`, and a `cors_origins_list` property that splits a comma-separated env var. Keep the existing `OPENROUTER_API_KEY` / `INTERVIEW_MODEL` keys and add `cv_screener_*` analogues; do **not** introduce a parallel `os.getenv` path.

**3. Two endpoints, not one** (`routers/screen.py`):

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness probe (Docker healthcheck, smoke tests) |
| `POST` | `/api/screen` | Full pipeline → JSON `{summary, matched_skills, missing_skills, strengths, concerns, score, recommendation, questions, reasoning}` |
| `POST` | `/api/screen/stream` | Same input, streams agent transitions as SSE so the UI can show "analyzer → scorer → questions" live |

The reference's SSE event taxonomy maps cleanly: rename `agent` → `agent` (same), `tool_call` is unused (we have no tools), keep `token` for live streaming, `done` for completion. The `astream_events(..., version="v2")` loop in `routers/agent.py:107` is the template — copy the structure, swap the node-name set.

**4. Typer CLI for dev/prod parity** (`cli.py`) — `api dev` (uvicorn with `--reload`) and `api serve` (production, configurable workers). Exposed via `[project.scripts]` in `pyproject.toml`:

```toml
[project.scripts]
api = "api.cli:app"
```

**5. Async LLM calls.** The reference uses `await llm.ainvoke(...)` inside async nodes — this is what makes SSE streaming responsive. Convert the current synchronous `llm.invoke(...)` calls in `interview.py` to `ainvoke` when promoting to FastAPI; the Streamlit path can stay sync.

## Docker setup

`docker-compose.yml` at repo root, services built from `apps/api/Dockerfile` (+ optional `apps/web/Dockerfile`). For the hackathon, **skip Postgres and Redis unless you're adding the LangGraph checkpointer for multi-session persistence** (currently a non-goal — see Non-goals above).

**Minimal compose (no persistence):**

```yaml
services:
  api:
    build: { context: ./apps/api, dockerfile: Dockerfile }
    env_file: .env
    ports: ["${API_PORT:-8000}:8000"]
    develop:
      watch:
        - { action: sync,    path: ./apps/api/src,           target: /app/src }
        - { action: rebuild, path: ./apps/api/pyproject.toml }

  web:
    build: { context: ./apps/web, dockerfile: Dockerfile }
    env_file: .env
    environment:
      API_URL: http://api:8000           # service name, not localhost — same docker network
    ports: ["8501:8501"]                 # streamlit default; 3000 if Next.js
    depends_on: [api]
```

If persistence becomes in-scope, add the `postgres` (postgres:16-alpine) and `redis` (redis:7-alpine) services from the reference's `docker-compose.yml` verbatim, plus `langgraph-checkpoint-postgres` to `pyproject.toml` and the `create_checkpointer()` pool from `agent/checkpointer.py`.

**API Dockerfile pattern** — multi-stage with uv, copy-lockfile-first for layer caching:

```dockerfile
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --no-dev --no-install-project
COPY src/ ./src/
RUN uv sync --no-dev

FROM python:3.12-slim AS runtime
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**`.env.example` at repo root** — list every variable the compose file references so a fresh clone is one `cp .env.example .env` + key paste away from runnable. Match the reference's section headers (`# ─── LLM ───`, `# ─── API ───`, etc.) for readability.

**Demo command:** `docker compose up --build` → API at `localhost:8000` (`/docs` for Swagger), UI at `localhost:8501` (Streamlit) or `localhost:3000` (Next.js). This is the live-demo entry point; rehearse it once before the hackathon.

## Build order (mapped to acceptance criteria)

Do these in order; each step lights up one acceptance-criteria checkbox. **Step 0 is done** — the file-layout split, FastAPI scaffolding, and Docker setup landed in the interview-prep refactor.

0. ~~Split `interview.py` into `agent/graph.py` + `agent/agents/*.py` + `agent/state.py`, add FastAPI + Docker scaffolding~~ ✅ done.
1. **Define `ScreeningState` and the parser agent.** New TypedDict in `agent/state.py` with all 13+ fields (cv_text, jd_text, cv_profile, jd_profile, parse_confidence, matched_skills, missing_skills, assessed_seniority, strengths, concerns, gaps, inconsistencies, bias_flags, risk_confidence, score, recommendation, questions, force_pass_gate_1, force_pass_gate_2). Implement `parser` agent. → unblocks every downstream step.
2. **Implement the three parallel assessment agents** (`skill_match`, `seniority`, `experience`) with the fan-out + join pattern. Each writes disjoint state keys. → satisfies "≥2 agents clearly involved" and the parallel-execution visibility.
3. **Implement `integrity_fairness` agent** writing `gaps`, `inconsistencies`, `bias_flags`, `risk_confidence`. → satisfies "Integrity & Fairness flags surfaced".
4. **Implement deterministic `scorer` (weighted 40/30/20/10) and `recommendation` (`>=8/5-7/<5`) as plain Python nodes.** → satisfies "score (0–10) + recommendation" and "deterministic weighted formula".
5. **Implement `interview_questions` agent with the skip-on-Reject conditional edge.** → satisfies "≥5 interview questions (except on Reject)".
6. **Wire the two HITL confidence gates** (`conf_gate_1` after parser, `conf_gate_2` after integrity) as `add_conditional_edges` routing to `human_review_*` sink nodes. → unblocks step 7.
7. **Build the Streamlit Approve/Override panel** that detects a `human_review_*` terminal state, renders the partial output, and on Approve re-invokes the graph with the `force_pass_gate_n` flag set. → satisfies "HITL gates trigger and resolve correctly".
8. **Hard-code the 3 golden-path scenarios into `agent/data/`** (sample_cvs.py + sample_jds.py) and add a Streamlit dropdown to load them. → satisfies the live-demo script.
9. **Build the Recruiter Report UI** — structured layout with score breakdown, flags, questions. Replaces the interview-prep chat layout entirely for the CV-Screener page. → satisfies "User submits CV + JD, structured evaluation returned".
10. *(Stretch)* Add the `/api/screen` + `/api/screen/stream` REST endpoints by copy-adapting `apps/api/src/api/routers/interview.py`. Renames the router and the graph node names referenced in the SSE event taxonomy. Not required for acceptance — the Streamlit UI alone satisfies every checkbox.

**Cutover strategy:** keep `apps/api/src/api/agent/graph.py` (interview-prep) alive until step 5 is green, then rename it to `interview_graph.py` and create a fresh `cv_screening_graph.py` next to it. The Streamlit interview-prep page stays runnable as a fallback demo through step 8.
