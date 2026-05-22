import streamlit as st
from langchain_core.runnables import RunnableConfig

from interview import graph

st.set_page_config(
    page_title="Interview Prep Workflow",
    page_icon="🎯",
    layout="centered",
)

st.title("🎯 Interview Prep Workflow")
st.caption(
    "Classifies your question, routes to a **technical**, **behavioral**, or "
    "**HR/career** coach, then a **delivery coach** adds tips."
)

AGENT_BADGE = {
    "technical": ("💻", "technical"),
    "behavioral": ("🗣️", "behavioral"),
    "hr_career": ("🧭", "hr/career"),
}

with st.sidebar:
    st.subheader("About")
    st.markdown(
        "- **Classifier** decides the question type.\n"
        "- **Router** sends it to the right specialist.\n"
        "- **Specialist** drafts a model answer.\n"
        "- **Delivery Coach** adds short, in-the-moment tips.\n\n"
        "Watch the steps light up as the graph runs."
    )
    if st.button("🧹 Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and msg.get("agent"):
            emoji, label = AGENT_BADGE.get(msg["agent"], ("🤖", msg["agent"]))
            st.caption(f"{emoji} answered as **{label}**")
        st.markdown(msg["content"])
        if msg.get("coach"):
            st.markdown("---")
            st.markdown(f"🧑‍🏫 **Coach**\n\n{msg['coach']}")


def run_graph_with_status(user_text: str):
    """Stream the graph and surface each node as it runs.

    Returns (specialist_reply, coach_reply, question_type).
    """
    specialist_reply = None
    coach_reply = None
    question_type = None

    # Build full conversation history from session state. The new user message
    # has already been appended to st.session_state.messages by the caller.
    # Coach tips are stored on the assistant entry under a separate key and are
    # NOT re-fed into the graph (they'd confuse the classifier).
    history = []
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            history.append({"role": "user", "content": msg["content"]})
        elif msg["role"] == "assistant" and msg.get("content"):
            history.append({"role": "assistant", "content": msg["content"]})

    with st.status("Running graph…", expanded=True) as status:
        graph_input = {
            "messages": history,
            "question_type": None,
            "coach_tips": None,
        }

        # Group this turn under a single named parent run in LangSmith.
        # Turn number = (existing user messages + 1) // 2 once we've appended.
        turn_number = sum(1 for m in st.session_state.messages if m["role"] == "user")
        run_config: RunnableConfig = {
            "run_name": "interview-turn",
            "tags": ["interview-prep", "streamlit"],
            "metadata": {"surface": "streamlit", "turn": turn_number},
        }

        for chunk in graph.stream(graph_input, config=run_config):
            for node_name, node_update in chunk.items():
                update = node_update or {}
                if node_name == "classifier":
                    question_type = update.get("question_type")
                    status.write(f"🧭 **Classifier** → `{question_type}`")
                elif node_name == "router":
                    emoji, label = AGENT_BADGE.get(question_type, ("🚦", question_type or "?"))
                    status.write(f"🚦 **Router** → {emoji} `{label}`")
                elif node_name in ("technical", "behavioral", "hr_career"):
                    emoji, label = AGENT_BADGE.get(node_name, ("🤖", node_name))
                    status.write(f"{emoji} **{label.title()} specialist** responding…")
                    messages = update.get("messages") or []
                    if messages:
                        last = messages[-1]
                        specialist_reply = (
                            last.content if hasattr(last, "content") else last["content"]
                        )
                elif node_name == "coach":
                    status.write("🧑‍🏫 **Delivery coach** adding tips…")
                    coach_reply = update.get("coach_tips")

        emoji, label = AGENT_BADGE.get(question_type, ("✅", "done"))
        status.update(
            label=f"{emoji} Answered as **{label}**",
            state="complete",
            expanded=False,
        )

    return specialist_reply, coach_reply, question_type


if prompt := st.chat_input("Paste an interview question…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        specialist_reply, coach_reply, question_type = run_graph_with_status(prompt)
        if specialist_reply is None:
            specialist_reply = "_(no response produced)_"
        if question_type:
            emoji, label = AGENT_BADGE.get(question_type, ("🤖", question_type))
            st.caption(f"{emoji} answered as **{label}**")
        st.markdown(specialist_reply)
        if coach_reply:
            st.markdown("---")
            st.markdown(f"🧑‍🏫 **Coach**\n\n{coach_reply}")

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": specialist_reply,
            "coach": coach_reply,
            "agent": question_type,
        }
    )
