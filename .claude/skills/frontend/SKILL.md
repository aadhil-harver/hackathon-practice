---
name: frontend
description: Build or extend a Streamlit UI that wraps a LangGraph multi-agent graph in this repo — page setup, sidebar, session state, streaming status panel, agent badges, and history wiring so the graph has multi-turn context.
---
# Frontend (Streamlit + LangGraph)

## Overview

In this project the "frontend" is **Streamlit** wrapping a compiled **LangGraph** graph from a sibling Python module (e.g. `main.py`, `interview.py`). Each Streamlit page does four things:

1. Reads/writes `st.session_state.messages` for display.
2. Reconstructs the conversation history and feeds it into `graph.stream(...)` per user turn.
3. Surfaces each node firing in a live `st.status` panel.
4. Renders the assistant reply (and any side outputs like coach tips) and appends to session state.

Use this skill when:
- A new LangGraph workflow exists in a `.py` module and needs a UI.
- An existing Streamlit page needs a new agent badge, sidebar control, or side-channel output rendered.

The existing references are `app.py` (dual-agent classifier demo) and `interview_app.py` (4-agent interview prep). Follow `interview_app.py` for anything with side-channel outputs or multi-turn context.

## Inputs

Before writing code, gather:
- **Graph module + variable name** — e.g. `from interview import graph`.
- **State schema** — the `TypedDict` fields. Pay attention to:
  - `messages: Annotated[list, add_messages]` — the conversation channel.
  - Any **side-channel fields** the graph writes (e.g. `coach_tips`, `question_type`, `next`).
- **Exact node names** — strings used in `graph_builder.add_node("name", fn)`. The status panel matches on these.
- **Classifier output values + node-name mapping** — e.g. classifier returns `"technical" | "behavioral" | "hr_career"` and node names match 1:1. If they don't match, the router translation lives in the graph file; mirror it in the UI badge dict.
- **Page metadata** — title, icon emoji, caption blurb.
- **Sidebar controls needed** — at minimum a "Clear conversation" button.

## Steps

1. **Read the graph file.** Confirm the import name, node names, state field names, and any side-channel state fields. Note the classifier `Literal` values.
2. **Page config + title.** `st.set_page_config(page_title=..., page_icon=..., layout="centered")`. Add a one-line `st.caption(...)` that explains the routing.
3. **`AGENT_BADGE` dict.** Map classifier output values → `(emoji, label)`. Use the same keys the classifier produces, not the node names, so re-rendering past turns works from stored `agent` field.
4. **Sidebar.** "About" markdown + a `🧹 Clear conversation` button that resets `st.session_state.messages` and reruns.
5. **Initialize + replay session state.** `if "messages" not in st.session_state: st.session_state.messages = []`. Loop through and re-render with `st.chat_message`, restoring the agent badge caption and any side-channel content (like coach tips) from the stored entry.
6. **`run_graph_with_status(user_text)`** — see template. Key behaviors:
   - Build `history` from `st.session_state.messages` *before* calling — the new user message is already appended at the call site.
   - Send ONLY `user` + main `assistant content` into the graph. Do **not** re-feed side-channel fields stored on entries (coach tips etc.) — they confuse the classifier.
   - Iterate `graph.stream(graph_input)`; switch on node name to update the status panel and capture outputs.
   - Read side-channel outputs from `update.get("<field_name>")`, not from `messages`.
7. **Chat input wiring.** `if prompt := st.chat_input(...):` → append user to session state → render user bubble → call the function → render assistant bubble (with badge caption + separator + side outputs) → append to session state.

## Guidelines

Pitfalls specific to this codebase — apply unless overridden:

- **Node names are a contract with the UI.** Renaming a node in the graph file silently breaks the `st.status` panel because `graph.stream` chunks key on those exact strings. Update both files together.
- **Keep classifier values and node names aligned.** This repo had drift in `main.py` (`emotional` → `therapist` mismatch handled in two places). Prefer 1:1 like `interview.py`. If you must drift, document the mapping in one place and reuse in both router and `AGENT_BADGE`.
- **Side-channel outputs go in their own state field, not in `messages`.** Otherwise the classifier sees them on the next turn as if they were real conversation. `interview.py`'s `coach_tips` is the pattern.
- **Streamlit does not persist graph state across turns** — every turn is a fresh `graph.invoke`. Multi-turn context must be rebuilt from `st.session_state.messages`. Don't try to thread a `state` dict between Streamlit reruns.
- **The LLM client lives in the graph file.** The Streamlit module imports `graph` only; do not instantiate `ChatOpenAI` / `init_chat_model` in `*_app.py`.
- **Env vars and secrets** load via `dotenv` inside the graph file, not in the Streamlit module.
- **No new dependencies without a reason.** This repo uses `uv` — if you genuinely need one, run `uv add <pkg>` and update `pyproject.toml`.
- **Out of scope** (don't build unless asked):
  - Login / auth
  - File uploads, resume parsing
  - Custom themes or dark mode
  - Mobile responsive tweaks
  - Charting libraries (a `st.progress` bar or `st.metric` is enough)

## Output Template

```python
import streamlit as st

from <GRAPH_MODULE> import graph  # e.g. `from interview import graph`

st.set_page_config(
    page_title="<PAGE_TITLE>",
    page_icon="<EMOJI>",
    layout="centered",
)

st.title("<EMOJI> <PAGE_TITLE>")
st.caption("<ONE_LINE_DESCRIPTION_OF_ROUTING>")

# Keys here are the classifier's output values (NOT node names, if they differ).
AGENT_BADGE = {
    "<classifier_value_1>": ("<emoji>", "<display label>"),
    "<classifier_value_2>": ("<emoji>", "<display label>"),
    # ...
}

with st.sidebar:
    st.subheader("About")
    st.markdown(
        "- **Classifier** decides ...\n"
        "- **Router** sends it to the right specialist.\n"
        "- **Specialist** answers.\n"
        "- (Optional) **Side agent** adds ...\n"
    )
    if st.button("🧹 Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = []

# Replay prior turns.
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and msg.get("agent"):
            emoji, label = AGENT_BADGE.get(msg["agent"], ("🤖", msg["agent"]))
            st.caption(f"{emoji} answered as **{label}**")
        st.markdown(msg["content"])
        # Render any stored side-channel content (e.g. coach tips).
        if msg.get("<SIDE_FIELD>"):
            st.markdown("---")
            st.markdown(f"<SIDE_HEADER>\n\n{msg['<SIDE_FIELD>']}")


def run_graph_with_status(user_text: str):
    """Stream the graph; surface each node in st.status; capture outputs."""
    specialist_reply = None
    side_reply = None  # rename per workflow (e.g. coach_reply)
    classification = None

    # Rebuild full conversation history. The new user message was appended
    # to st.session_state.messages before this function was called.
    # Only send user + main assistant content; NEVER side-channel outputs.
    history = []
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            history.append({"role": "user", "content": msg["content"]})
        elif msg["role"] == "assistant" and msg.get("content"):
            history.append({"role": "assistant", "content": msg["content"]})

    with st.status("Running graph…", expanded=True) as status:
        graph_input = {
            "messages": history,
            # Initialize every state field the graph reads. Set to None.
            "<CLASSIFIER_FIELD>": None,
            "<SIDE_FIELD>": None,
        }

        for chunk in graph.stream(graph_input):
            for node_name, node_update in chunk.items():
                update = node_update or {}
                if node_name == "classifier":
                    classification = update.get("<CLASSIFIER_FIELD>")
                    status.write(f"🧭 **Classifier** → `{classification}`")
                elif node_name == "router":
                    emoji, label = AGENT_BADGE.get(classification, ("🚦", classification or "?"))
                    status.write(f"🚦 **Router** → {emoji} `{label}`")
                elif node_name in (<TUPLE_OF_SPECIALIST_NODE_NAMES>):
                    emoji, label = AGENT_BADGE.get(node_name, ("🤖", node_name))
                    status.write(f"{emoji} **{label.title()} specialist** responding…")
                    messages = update.get("messages") or []
                    if messages:
                        last = messages[-1]
                        specialist_reply = (
                            last.content if hasattr(last, "content") else last["content"]
                        )
                elif node_name == "<SIDE_NODE_NAME>":
                    status.write("<EMOJI> **<SIDE_NODE_LABEL>** running…")
                    side_reply = update.get("<SIDE_FIELD>")

        emoji, label = AGENT_BADGE.get(classification, ("✅", "done"))
        status.update(
            label=f"{emoji} Answered as **{label}**",
            state="complete",
            expanded=False,
        )

    return specialist_reply, side_reply, classification


if prompt := st.chat_input("<INPUT_PLACEHOLDER>"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        specialist_reply, side_reply, classification = run_graph_with_status(prompt)
        if specialist_reply is None:
            specialist_reply = "_(no response produced)_"
        if classification:
            emoji, label = AGENT_BADGE.get(classification, ("🤖", classification))
            st.caption(f"{emoji} answered as **{label}**")
        st.markdown(specialist_reply)
        if side_reply:
            st.markdown("---")
            st.markdown(f"<SIDE_HEADER>\n\n{side_reply}")

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": specialist_reply,
            "<SIDE_FIELD>": side_reply,
            "agent": classification,
        }
    )
```

### Run command

```bash
uv run streamlit run <new_file>.py
```