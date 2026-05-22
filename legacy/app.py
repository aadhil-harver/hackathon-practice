import streamlit as st

from main import graph

st.set_page_config(
    page_title="Dual-Agent Chatbot",
    page_icon="🧠",
    layout="centered",
)

st.title("🧠 Dual-Agent Chatbot")
st.caption("Classifies your message, then routes to a **therapist** or **logical** agent.")

AGENT_BADGE = {
    "emotional": ("🫶", "therapist"),
    "logical": ("🧮", "logical"),
}

with st.sidebar:
    st.subheader("About")
    st.markdown(
        "- **Classifier** decides if your message is emotional or logical.\n"
        "- **Router** sends it to the right agent.\n"
        "- The agent answers in its own voice.\n\n"
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


def run_graph_with_status(user_text: str):
    """Stream the graph and surface each node as it runs. Returns (reply, message_type)."""
    reply_text = None
    message_type = None

    with st.status("Running graph…", expanded=True) as status:
        graph_input = {
            "messages": [{"role": "user", "content": user_text}],
            "message_type": None,
        }

        for chunk in graph.stream(graph_input):
            for node_name, node_update in chunk.items():
                update = node_update or {}
                if node_name == "classifier":
                    message_type = update.get("message_type")
                    status.write(f"🧭 **Classifier** → `{message_type}`")
                elif node_name == "router":
                    target = "therapist" if message_type == "emotional" else "logical"
                    status.write(f"🚦 **Router** → `{target}`")
                elif node_name in ("therapist", "logical"):
                    emoji, label = AGENT_BADGE.get(
                        "emotional" if node_name == "therapist" else "logical",
                        ("🤖", node_name),
                    )
                    status.write(f"{emoji} **{label.title()} agent** responding…")
                    messages = update.get("messages") or []
                    if messages:
                        last = messages[-1]
                        reply_text = last.content if hasattr(last, "content") else last["content"]

        emoji, label = AGENT_BADGE.get(message_type, ("✅", "done"))
        status.update(
            label=f"{emoji} Answered as **{label}**",
            state="complete",
            expanded=False,
        )

    return reply_text, message_type


if prompt := st.chat_input("Tell me what's on your mind…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        reply, message_type = run_graph_with_status(prompt)
        if reply is None:
            reply = "_(no response produced)_"
        if message_type:
            emoji, label = AGENT_BADGE.get(message_type, ("🤖", message_type))
            st.caption(f"{emoji} answered as **{label}**")
        st.markdown(reply)

    st.session_state.messages.append(
        {"role": "assistant", "content": reply, "agent": message_type}
    )
