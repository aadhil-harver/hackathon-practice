# CV-Screener — Demo Brief

## 1 · What it does (60-second pitch)

A recruiter or technical interviewer drops a CV file and pastes a JD into the tool. 
In under a minute they get back a structured hiring recommendation: a parsed candidate profile, matched/missing skills, strengths/concerns,
integrity & fairness flags, a defensible weighted score out of 10, a deterministic **Shortlist / Hold / Reject** call, and ≥5 tailored interview questions
— exportable as a PDF. The work is split across **8 specialised agents in a LangGraph pipeline** so each judgment call (parsing, skill match, 
seniority assessment, experience fit, integrity check, scoring, recommendation, question generation) is inspectable, testable, 
and **defensible** rather than a black-box prompt.

## 2 · Architecture at a glance

```
START → input_handler → parser → ✋ conf_gate_1 ─── low conf ──► human_review_1 (END)
                                       │
                                       ▼ pass
                                   ┌─ skill_match  ┐  ← three agents
                                   ├─ seniority    │  fire in PARALLEL
                                   └─ experience   ┘  (LangGraph fan-out)
                                       │
                                       ▼ join
                                   integrity ─► ✋ conf_gate_2 ─ high risk ─► human_review_2 (END)
                                                                │
                                                                ▼ pass
                                                            scorer (deterministic Python)
                                                                │
                                                                ▼
                                                            recommendation ─ Reject ─► END
                                                                │
                                                                ▼ else
                                                            interview_questions → END
```

**Why a graph, not a single prompt?** Three reasons judges should hear:

- **Inspectability** — every agent's output is a separate state key, visible live in the UI status panel and traceable in LangSmith. If the recommendation looks wrong, you can see exactly which agent introduced the error.
- **Defensibility** — the score-to-recommendation mapping is **pure Python** (`>=8 Shortlist / 5-7 Hold / <5 Reject`). The LLM never proposes the recommendation directly, so it can never contradict the score it just produced. Running the same inputs twice gives the same recommendation.
- **Concurrency** — `skill_match`, `seniority`, and `experience` write disjoint state keys and run **simultaneously**. The UI tags them `(parallel 1/3 · 2/3 · 3/3)` as they emit.

## 3 · Tool stack and rationale

| Choice | Picked over | Why |
| --- | --- | --- |
| **LangGraph** | Plain LangChain agents, CrewAI, custom orchestration | Explicit graph topology means we can show parallel fan-out + HITL gates as **first-class edges**, not buried inside an agent's prompt. `stream(mode='updates')` is what powers the live status panel. |
| **OpenRouter + `anthropic/claude-sonnet-4.6`** | Direct Anthropic / OpenAI API | One key, model-portable (`INTERVIEW_MODEL` env var swaps in any model). Lets us demo on free credit during hackathon and switch to a paid account later without touching code. |
| **`with_structured_output(PydanticModel)`** | Free-form JSON parsing | Every agent's output is a typed Pydantic model — invalid output throws at the LLM boundary, not three steps later in the scorer. |
| **Streamlit** | FastAPI + React / Next.js | The hackathon scoring criterion is "working demo > polished idea". Streamlit gets us a multi-page UI with file upload, live status, download button in ~500 lines. (FastAPI scaffolding is still there at `apps/api/src/api/main.py` for the stretch goal.) |
| **`pypdf` + `python-docx`** | PyMuPDF / Apache Tika | Pure Python, MIT-licensed, no system deps. Handles 95% of real-world CVs. Scanned/image-only PDFs would need OCR (tesseract), which we explicitly scoped out. |
| **ReportLab** | WeasyPrint, HTML→PDF | Pure Python, no system deps (no Cairo/Pango). The Platypus flowable model keeps the layout code declarative. |
| **`pydantic-settings`** | Raw `os.getenv` | One `Settings` class with type validation; the FastAPI app loads it once via `@lru_cache`. |
| **`uv`** | pip / poetry | Fast, lockfile-driven, what the reference monorepo uses. `uv run api dev` / `uv run streamlit run …` is the demo entry. |
| **Docker Compose** | bare-metal | Single `docker compose up --build` boots the API on `:8000`. Web UI runs locally (Streamlit doesn't need to be containerised for the demo). |
| **LangSmith** *(optional)* | DIY tracing | Each run is grouped under a `cv-screening-run` parent so judges can pull up the full trace if they ask. |

## 4 · Design decisions worth defending

These are the choices that will likely come up:

**a) The score is computed by Python, not the LLM.**
The LLM produces *components* (matched_skills list, assessed_seniority, etc.) — the deterministic scorer in `apps/api/src/api/agent/scoring.py` applies a fixed `0.4·skills + 0.3·seniority + 0.2·domain + 0.1·education` formula. Each sub-score is itself a pure function of the LLM's structured outputs. **Anyone can audit the scorer**, and re-running the same inputs gives the same recommendation — that's the contract.

**b) Two HITL confidence gates, not "human in the loop everywhere".**
The gates trigger when **`parse_confidence < 0.6`** (after parsing) or **`risk_confidence < 0.6`** (after integrity & fairness). The Streamlit UI shows the partial output and asks the recruiter to Approve or Stop. On Approve, the graph is re-invoked with a `force_pass_gate_N=True` flag in state, and **every already-completed LLM node short-circuits via skip-if-cached** so the resume costs only what's downstream.

**c) Bias signals are flagged, never used to filter.**
The Integrity & Fairness agent emits a `bias_flags` list — "graduation year reveals age band", "career gap that's plausibly parental leave" — but the scorer never sees them. They appear in the report so the recruiter is *aware* of signals they might unconsciously act on. The agent's prompt explicitly says "FLAG, DO NOT FILTER".

**d) Adaptive `max_tokens` retry.**
Free-tier OpenRouter budgets fluctuate per request. The 402 error message tells us exactly what's affordable ("can only afford 978"); the shared `_invoke_with_retry` helper parses that and retries with a small safety margin. Every LLM node gets this for free. If the retry also fails (genuinely insufficient credit), the Streamlit `try/except` catches it and renders the report from whatever made it through.

**e) Skip-on-Reject.**
The `interview_questions` node is wired through a `conditional_edges` that routes to END when `recommendation == "Reject"`. No point spending tokens generating interview questions for a candidate the deterministic scorer already rejected.

**f) `TypedDict(total=False)` for state.**
17 optional state keys, each owned by exactly one agent. No reducer functions, no merge conflicts on the parallel fan-out. The TypedDict is documented inline (`apps/api/src/api/agent/state.py`) — that's the contract every agent reads from.

## 5 · Resilience & UX features

| Feature | What it does | Where |
| --- | --- | --- |
| **Live agent badges** | `stream(mode='updates')` surfaces each agent as it fires, with a tailored one-line summary per node (parser shows `parse_confidence`, scorer shows `9/10`, parallel agents are tagged `1/3`, `2/3`, `3/3`). | `_run_graph` in `cv_screener_app.py` |
| **HITL Approve / Stop panel** | Pause/resume without a checkpointer — the paused state is held in `st.session_state` between Streamlit reruns. | `_hitl_panel` in `cv_screener_app.py` |
| **Adaptive token retry** | Auto-retries any LLM call at the budget OpenRouter reports it can afford. | `_invoke_with_retry` in `cv_screening_graph.py` |
| **Graceful partial-failure** | If a downstream node fails (typically the questions agent on tight budgets), the upstream score + recommendation still render. | `_run_graph` `try/except` |
| **File upload** | Drop PDF / DOCX / TXT; text is extracted, shown in an editable textarea (recruiter can correct extraction artifacts before running). | `apps/api/src/api/extract.py` + `st.file_uploader` |
| **Golden-path dropdown** | Three canned scenarios (Shortlist / Hold / Reject) load into the inputs with one click — the demo doesn't depend on typing accuracy. | `apps/api/src/api/agent/data/golden_paths.py` |
| **PDF export** | Full recruiter report rendered to PDF via ReportLab, filename includes candidate name + recommendation + timestamp. | `apps/api/src/api/export.py` + `st.download_button` |
| **Skip-if-cached on every LLM node** | HITL resume costs only downstream tokens; re-running the parser on resume would risk a different `parse_confidence` that re-trips the gate. | Every node in `cv_screening_graph.py` |
| **`max_tokens` cap** | Load-bearing — without it, `ChatOpenAI` sends the model's max (65k), which low-credit OpenRouter accounts can't afford. | `apps/api/src/api/agent/llm.py` |

## 6 · What's intentionally out of scope (defensible non-goals)

If a judge asks "why didn't you do X", these are the answers we already agreed to in CLAUDE.md:

- **Human Override (mid-pipeline weight adjustment)** — out for v1. The 40/30/20/10 weights are baked. We deferred this to keep the deterministic-Python contract clean; the right place to add it is between `scorer` and `recommendation`.
- **Real LangGraph `interrupt_before` + Postgres checkpointer** — we use the lighter "hard-stop + force_pass flag" pattern. Keeps Docker Compose to a single service (no Postgres dependency).
- **Multi-CV batch screening, ATS integration, candidate-facing UI** — judges-visible UI is the single-CV-per-run flow.
- **OCR for image-only PDFs** — would need tesseract (system dep). The extractor raises a friendly error pointing recruiters at "re-export with a text layer".
- **Fine-tuning, custom embeddings, RAG over JD corpus** — single-shot LLM calls per agent are enough. Adding embeddings would dilute Correctness without proportional gain on the scoring rubric.

## 7 · Demo cheat sheet (3 scenarios)

Run with `uv run streamlit run apps/web/cv_screener_app.py`. Sidebar → pick a golden path → Load → Run.

| Scenario | Inputs | Expected | Demonstrates |
| --- | --- | --- | --- |
| **1 · Shortlist** | Sarah Chen (8y senior Python/AWS/fintech) vs. Senior Backend JD | Score 8-10 → **Shortlist** | Happy path: parser → 3-way parallel → integrity → deterministic score → 5+ questions, all visible in the status panel. |
| **2 · Hold** | Mark Rivera (2y frontend, some Python) vs. same JD | Score 5-7 → **Hold** | Borderline: `missing_skills` non-empty, reasoning cites the gap, questions probe the missing areas. |
| **3 · Reject** | Priya Desai (marketing manager) vs. same JD | Score < 5 → **Reject** | Negative path: scorer produces a low score, `interview_questions` is skipped via conditional edge. Report still renders cleanly. |

For **HITL demo**: deliberately feed a vague / one-line CV that drops `parse_confidence` below 0.6. The pipeline pauses; click Approve and watch the rest run with skip-if-cached.

## 8 · Likely judge questions — pre-canned answers

**Q: Why eight agents instead of one prompt?**
A: Each agent is one judgment call. Separating them lets us inspect failures (which agent went wrong?), run three in parallel (visible win on Technical Depth), and keep the deterministic score contract — the LLM never sees the final recommendation logic.

**Q: How do you stop the LLM from inventing skills the CV doesn't claim?**
A: Two layers. (1) The skill_match prompt explicitly says "only include skills that appear in `cv_profile.skills` — do NOT infer from project descriptions". (2) The downstream scorer compares against the *parser's* extracted skill list, not the LLM's free-text interpretation. The parser is the only agent allowed to extract skills.

**Q: What if the parser gets the seniority wrong?**
A: Two safeguards. The seniority agent re-assesses independently (it doesn't trust the parser's call), citing specific CV items as evidence. And gate #1's `parse_confidence < 0.6` threshold sends low-confidence parses to the recruiter for review before downstream work runs.

**Q: How does it handle bias?**
A: The Integrity & Fairness agent surfaces bias signals (graduation year revealing age, gendered phrasing, gaps that could be parental leave) but the scorer never sees them. The recruiter sees the flags in the report. It's an awareness mechanism, not an automated filter.

**Q: How much does a run cost?**
A: 8 LLM calls per run, each ~200-1200 tokens. On Claude Sonnet 4.6 via OpenRouter, a typical full Shortlist run is ~$0.05-0.10. Reject runs are cheaper (~$0.03) because questions are skipped.

**Q: Could this scale to batch screening?**
A: Yes — the graph is stateless, so you'd loop `screening_graph.invoke()` over a queue of (CV, JD) pairs. Out of scope for the hackathon but mechanically straightforward; the obvious add-on is a Postgres checkpointer for resumable batch jobs.

**Q: What's the most fragile part?**
A: The parser's `candidate_name` extraction depends on the CV having a recognisable header — anonymised CVs return `None` (handled in the UI fallback). Token budgets on free OpenRouter accounts can squeeze the questions agent; the adaptive retry handles fluctuations down to ~400 tokens, below which the report still renders without the questions section.

**Q: How would you add a ninth agent (e.g. cultural fit)?**
A: Three files. (1) New `agents/cultural_fit.py` with a Pydantic schema + prompt. (2) Add the output keys to `ScreeningState`. (3) Add the node + edges to `cv_screening_graph.py`. Pattern is identical to the existing agents.
