# Hackathon Practice — Dual-Agent Chatbot

A LangGraph chatbot that classifies each message and routes it to either a **therapist** or **logical** agent. Includes a Streamlit UI that shows the routing steps live.

## What's in here

| File | Purpose |
|------|---------|
| `main.py` | LangGraph definition: classifier → router → therapist / logical agents. Runs as a CLI loop when executed directly. |
| `simple.py` | Minimal single-node chatbot for reference. |
| `app.py` | Streamlit UI wrapping `main.py`'s graph, with live step display. |

## Prerequisites

- Python **3.10+** (see `.python-version`)
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- A **Groq API key** (the LLM is `groq:llama-3.3-70b-versatile`)

## Setup

```bash
# 1. Install dependencies into a local .venv
uv sync

# 2. Create your .env file
echo "GROQ_API_KEY=your_key_here" > .env
```

## Run

### Streamlit UI (recommended for demos)

```bash
uv run streamlit run app.py
```

Then open <http://localhost:8501>. As you chat, an expandable status panel shows each graph step (`Classifier → Router → Agent`) before collapsing to a one-line badge.

### CLI — routed chatbot

```bash
uv run python main.py
```

Type messages at the `Message:` prompt. Type `exit` to quit.

### CLI — simple single-agent chatbot

```bash
uv run python simple.py
```

Prompts for one message, prints one reply, and exits.

## Troubleshooting

- **`GROQ_API_KEY` not found** — confirm `.env` exists at the repo root and contains the key. `.env` is git-ignored.
- **Port 8501 already in use** — pass a different port: `uv run streamlit run app.py --server.port 8502`.
- **Streamlit not reloading** — install Watchdog for faster reloads: `uv pip install watchdog`.
