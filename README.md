# CV-Screener

A multi-agent LangGraph workflow that screens a candidate CV against a job description and returns a structured hiring recommendation in under a minute. Built for the Gapstars AI Hackathon (May 22).

The recruiter uploads a CV (PDF / DOCX / TXT), pastes a JD, and gets back: matched / missing skills, assessed seniority, strengths and concerns, integrity & fairness flags, a deterministic weighted score out of 10, a **Shortlist / Hold / Reject** call, and ≥5 tailored interview questions — exportable as a PDF.

```
START → input_handler → parser → ✋ conf_gate_1 ──► human_review_1 (END)
                                       │ pass
                                       ▼
                                   ┌─ skill_match  ┐
                                   ├─ seniority    │  ← three agents in PARALLEL
                                   └─ experience   ┘
                                       │
                                       ▼  (join)
                                   integrity ─► ✋ conf_gate_2 ──► human_review_2 (END)
                                                  │ pass
                                                  ▼
                                              scorer (deterministic Python)
                                                  │
                                                  ▼
                                              recommendation ─ Reject ─► END
                                                  │ else
                                                  ▼
                                              interview_questions → END
```

Full design diagram in mermaid: [`docs/recruiter_screening.mmd`](docs/recruiter_screening.mmd). Demo-ready brief with rationale for every tool choice and pre-canned judge Q&A: [`docs/DEMO_BRIEF.md`](docs/DEMO_BRIEF.md). Project-level instructions for working in this repo: [`CLAUDE.md`](CLAUDE.md).

## Quick start

```bash
# 1. Install dependencies
uv sync

# 2. Configure the LLM key
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY=sk-or-v1-...

# 3. Run the Streamlit demo
uv run streamlit run apps/web/cv_screener_app.py
```

Then open <http://localhost:8501>. Use the **sidebar dropdown** to load one of the three canned golden-path scenarios (Shortlist / Hold / Reject), click **▶ Run screening**, and watch each agent fire in the status panel.

## Prerequisites

- Python **3.10+** (pinned in `.python-version`)
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- An **OpenRouter API key** — get one at <https://openrouter.ai/keys>. The LLM defaults to `anthropic/claude-sonnet-4.6`; override via `INTERVIEW_MODEL` to use any other OpenRouter-supported model.
- *(Optional)* A **LangSmith API key** for tracing — runs are grouped under a `cv-screening-run` parent.

## Run options

### Streamlit UI — primary demo surface

```bash
uv run streamlit run apps/web/cv_screener_app.py
```

- File uploader for CV (PDF / DOCX / TXT) — text is extracted and shown in an editable textarea.
- Sidebar dropdown with three golden-path scenarios.
- Live agent badges as the graph runs (parallel fan-out tagged `1/3 · 2/3 · 3/3`).
- HITL Approve / Stop panel when `parse_confidence < 0.6` or `risk_confidence < 0.6`.
- Recruiter Report with score breakdown, matched / missing skills, strengths / concerns, integrity flags, interview questions.
- "📄 Export report as PDF" download button on completed runs.

### Interview-prep workflow (legacy)

The earlier interview-prep chatbot is still functional at `apps/web/streamlit_app.py`:

```bash
uv run streamlit run apps/web/streamlit_app.py
```

Classifier → router → (technical / behavioral / hr_career) → coach. Useful as a multi-turn LangGraph reference; not the hackathon submission.

### FastAPI backend

```bash
uv run api dev                       # hot-reload dev server on 127.0.0.1:8000
uv run api serve --workers 4         # production server
```

Endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness probe |
| `POST` | `/api/interview` | One-shot interview-prep response |
| `POST` | `/api/interview/stream` | Same input, streams agent transitions as SSE |

Open <http://127.0.0.1:8000/docs> for Swagger.

### Docker Compose

```bash
docker compose up --build
```

API on `:8000`. Streamlit is run locally (no need to containerise for the demo).

## Configuration

Every setting is read from `.env` at the repo root. See [`.env.example`](.env.example) for the full list. Key vars:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | *(required)* | OpenRouter credential — every LLM call goes through this |
| `INTERVIEW_MODEL` | `anthropic/claude-sonnet-4.6` | Swap to any OpenRouter-supported model without touching code |
| `INTERVIEW_MAX_TOKENS` | `800` | Per-request output cap. Load-bearing on low-credit OpenRouter accounts (without it, `ChatOpenAI` sends max=65k which gets rejected) |
| `QUESTIONS_MAX_TOKENS` | `1200` | Higher cap for the questions agent specifically — it emits ≥5 structured items and needs more output budget |
| `LANGSMITH_TRACING` | `false` | Set to `true` (with `LANGSMITH_API_KEY`) to send traces to LangSmith |
| `LANGSMITH_PROJECT` | `interview-prep` | Project name for grouping traces |
| `API_PORT` | `8000` | Where the FastAPI server binds |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:8501` | Comma-separated list for the API's CORS middleware |

## Project structure

```
hackathon-practice/
├── apps/
│   ├── api/
│   │   ├── Dockerfile
│   │   └── src/api/
│   │       ├── main.py              # FastAPI app factory + lifespan + CORS
│   │       ├── config.py            # pydantic-settings Settings class
│   │       ├── cli.py               # Typer CLI: `api dev` / `api serve`
│   │       ├── extract.py           # PDF / DOCX / TXT → text
│   │       ├── export.py            # ReportLab → recruiter-report PDF
│   │       ├── agent/
│   │       │   ├── cv_screening_graph.py    # The 8-agent CV-Screener graph
│   │       │   ├── graph.py                 # Legacy interview-prep graph
│   │       │   ├── state.py                 # InterviewState + ScreeningState TypedDicts
│   │       │   ├── llm.py                   # Shared OpenRouter LLM factory
│   │       │   ├── scoring.py               # Deterministic weighted-score logic
│   │       │   ├── agents/                  # One file per agent (prompt + schema)
│   │       │   │   ├── parser.py
│   │       │   │   ├── skill_match.py
│   │       │   │   ├── seniority.py
│   │       │   │   ├── experience.py
│   │       │   │   ├── integrity.py
│   │       │   │   ├── questions.py
│   │       │   │   └── [classifier, technical, behavioral, hr_career, coach]  # interview-prep
│   │       │   └── data/
│   │       │       ├── sample_cvs.py        # Three golden-path CVs
│   │       │       ├── sample_jds.py
│   │       │       └── golden_paths.py      # Scenario dataclass + lookup
│   │       └── routers/
│   │           └── interview.py             # FastAPI routes for interview-prep
│   └── web/
│       ├── cv_screener_app.py       # **Main demo UI**
│       └── streamlit_app.py         # Legacy interview-prep UI
├── docs/
│   ├── DEMO_BRIEF.md                # Demo cheat sheet + judge Q&A
│   └── recruiter_screening.mmd      # Source-of-truth design diagram (mermaid)
├── legacy/                          # Pre-refactor therapy/logical chatbot
├── docker-compose.yml
├── .env.example
├── .streamlit/config.toml           # Harver-aligned theme
└── CLAUDE.md                        # Project instructions for Claude Code
```

## Architecture in one paragraph

The CV-Screener is a LangGraph `StateGraph` with eight agents. Six are LLM-backed (parser, skill_match, seniority, experience, integrity, interview_questions); two are deterministic Python (scorer, recommendation). The three middle agents fan out in parallel from the parser and join at the integrity node. Two human-in-the-loop confidence gates can pause the pipeline (`parse_confidence < 0.6` after parsing, `risk_confidence < 0.6` after integrity); the Streamlit UI captures the partial state and resumes via `force_pass_gate_N=True` flags. Every LLM node uses **skip-if-cached** so HITL resume costs only downstream tokens. The deterministic scorer applies a `0.4·skills + 0.3·seniority + 0.2·domain + 0.1·education` weighted formula; the recommendation is a pure mapping from the integer score (`>=8 Shortlist / 5-7 Hold / <5 Reject`). The interview-questions agent is conditionally skipped when the recommendation is Reject. See [`docs/DEMO_BRIEF.md`](docs/DEMO_BRIEF.md) for the full rationale.

## Troubleshooting

**`OPENROUTER_API_KEY` not found** — `.env` must be at the repo root, not under `apps/api/`. Confirm with `ls -la .env`.

**HTTP 402 — "can only afford N tokens"** — Your OpenRouter account is on free credit and the per-request cap is below what an agent asked for. **The graph auto-retries every LLM call at the budget OpenRouter reports it can afford** (see `_invoke_with_retry` in `cv_screening_graph.py`), so most runs will still complete. If `affordable` drops below the floor (200 for most agents, 400 for the questions agent), the report will render without the affected section. **Fix**: top up at <https://openrouter.ai/settings/credits>.

**`python-dotenv could not parse statement starting at line X`** — A line in `.env` doesn't match `KEY=value` format. Common causes: spaces around `=`, smart quotes (`"` → `“ ”`), or a value with a real newline mid-line. dotenv silently skips the line and keeps parsing the rest.

**Port 8501 already in use** — `uv run streamlit run apps/web/cv_screener_app.py --server.port 8502`.

**Streamlit not reloading on file changes** — `uv pip install watchdog`.

**PDF extraction returns no text** — likely a scanned / image-only PDF with no text layer. OCR is out of scope; re-export the CV with a text layer. The `apps/api/src/api/extract.py` extractor raises a clear `CVExtractionError` with this message.

**Graph node names look wrong in the status panel** — `apps/web/cv_screener_app.py`'s `AGENT_DISPLAY` dict must match the node names registered in `cv_screening_graph.py`. Renaming a node breaks the status panel silently.

## Acceptance criteria

- ✅ User submits CV + JD through the UI (textarea or file upload).
- ✅ Structured evaluation returned (not free-form prose).
- ✅ Score (0–10) + recommendation surfaced.
- ✅ Score produced by deterministic weighted formula, not the LLM.
- ✅ Reasoning cites specific CV evidence (strengths/concerns name profile items).
- ✅ Integrity & Fairness flags surfaced.
- ✅ ≥5 interview questions (skipped on Reject).
- ✅ ≥2 agents clearly visible in the run — 8 agents fire, with the parallel fan-out tagged in the UI.
- ✅ HITL gates trip and resolve correctly.

## License

Hackathon submission. No public license; internal use only.
