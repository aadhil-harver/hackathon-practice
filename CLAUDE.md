# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

Dependencies are managed with `uv` (see `.python-version` for the pinned Python). All runtime commands go through `uv run`:

```bash
uv sync                              # install deps into .venv
uv run streamlit run app.py          # Streamlit UI (default port 8501)
uv run python main.py                # CLI routed chatbot (type "exit" to quit)
uv run python simple.py              # one-shot single-agent chatbot
```

A `GROQ_API_KEY` in `.env` at the repo root is required — the LLM is hard-coded to `groq:llama-3.3-70b-versatile` in both `main.py` and `simple.py`.

There is no test suite, linter, or formatter configured.

## Architecture

The project is a LangGraph demo with three entry points that share one graph definition.

**`main.py` owns the graph.** It builds a four-node `StateGraph`:

```
START → classifier → router → (therapist | logical) → END
```

- `State` is a `TypedDict` with `messages` (using the `add_messages` reducer so updates append) and `message_type`.
- `classify_message` uses `llm.with_structured_output(MessageClassifier)` — a Pydantic model with a `Literal["emotional", "logical"]` field — to force a typed classification.
- `router` is itself a node that returns `{"next": "..."}`; the actual branching is a `conditional_edges` call that reads `state["next"]`. Note this means `next` lives in state but is not declared in the `State` TypedDict — LangGraph tolerates this, but adding type-checking would surface it.
- `therapist_agent` and `logical_agent` both only look at `state["messages"][-1]` (the latest user turn) — they do **not** see prior conversation history when forming a reply, even though `add_messages` keeps the full history in state.

**`app.py` wraps the same graph.** It imports `graph` from `main` and uses `graph.stream(...)` to surface each node as it fires inside a `st.status` panel. The Streamlit session keeps its own `st.session_state.messages` list for display; it does **not** persist LangGraph state across turns — each user message is sent into the graph as a fresh single-message input. Don't expect multi-turn memory in the UI.

**`simple.py` is a standalone reference.** A one-node graph with no classifier/router; useful as a minimal example but not imported anywhere.

## Things to watch for when changing this code

- `app.py` depends on the exact node names (`classifier`, `router`, `therapist`, `logical`) emitted by `graph.stream` to render status updates. Renaming a node in `main.py` will silently break the status panel.
- The classifier prompt produces values `"emotional" | "logical"`, but the router maps them to node names `"therapist" | "logical"`. The two naming systems are bridged in `router()` and again in `app.py`'s `AGENT_BADGE` dict — keep both in sync if you add a third agent.
- Both agents discard chat history (see above). If you need conversational continuity, change the `messages = [...]` construction in `therapist_agent` / `logical_agent` to pass the full `state["messages"]` instead of only the last one.
