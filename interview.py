import os

from dotenv import load_dotenv
from typing import Annotated, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

load_dotenv()

# LangSmith tracing — opt-in via env. If LANGSMITH_TRACING=true and
# LANGSMITH_API_KEY are set in .env, LangChain/LangGraph auto-send traces.
# Default the project name here so traces land in "interview-prep" instead of
# the catch-all "default" project. Users can override via LANGSMITH_PROJECT.
os.environ.setdefault("LANGSMITH_PROJECT", "interview-prep")

# OpenRouter is OpenAI-compatible: point ChatOpenAI at its base_url and use
# OPENROUTER_API_KEY. Default model is Claude Sonnet 4.6 (strongest Sonnet
# currently on OpenRouter); override with INTERVIEW_MODEL.
_OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not _OPENROUTER_API_KEY:
    raise RuntimeError(
        "OPENROUTER_API_KEY is not set. Add it to .env at the repo root. "
        "Get a key from https://openrouter.ai/keys"
    )

llm = ChatOpenAI(
    model=os.getenv("INTERVIEW_MODEL", "anthropic/claude-sonnet-4.6"),
    base_url="https://openrouter.ai/api/v1",
    api_key=_OPENROUTER_API_KEY,
    temperature=0.3,
    # OpenRouter enforces an upper-bound check against remaining credit. Without
    # this cap, ChatOpenAI sends max_tokens=<model max> (65536 on Sonnet 4.6),
    # which low-credit accounts cannot afford. Our prompts target ~350 words, so
    # 1500 is comfortable headroom.
    max_tokens=int(os.getenv("INTERVIEW_MAX_TOKENS", "800")),
)


class QuestionClassifier(BaseModel):
    question_type: Literal["technical", "behavioral", "hr_career"] = Field(
        ...,
        description=(
            "Classify the interview question as 'technical' (coding, DSA, system design, "
            "language-specific), 'behavioral' (tell-me-about-a-time, STAR-style), or "
            "'hr_career' (why this company, salary, strengths/weaknesses, career goals)."
        ),
    )


class InterviewState(TypedDict):
    messages: Annotated[list, add_messages]
    question_type: str | None
    coach_tips: str | None


def _history_as_dicts(messages):
    """Convert LangChain message objects into role/content dicts for LLM calls."""
    out = []
    for msg in messages:
        role = "user" if getattr(msg, "type", None) == "human" else "assistant"
        out.append({"role": role, "content": msg.content})
    return out


def classify_question(state: InterviewState):
    classifier_llm = llm.with_structured_output(QuestionClassifier)

    history = _history_as_dicts(state["messages"])

    system_msg = {
        "role": "system",
        "content": """You classify the user's LATEST interview-prep message into one of three buckets.

        STEP 1 — Decide if the latest message is a STANDALONE question or a FOLLOW-UP.
        It is a follow-up if it does any of the following with respect to prior turns:
          - refines the role/context (e.g. "this role is more business-focused",
            "actually it's a backend position", "for a junior level")
          - asks for adjustment of the previous answer (e.g. "make it shorter",
            "give me another example", "try again", "go deeper")
          - is a short fragment that only makes sense in context

        If it is a FOLLOW-UP, classify it using the TOPIC of the most recent
        substantive user question, NOT the follow-up text alone. Stick with the
        prior bucket unless the user has clearly switched topic.

        STEP 2 — Pick the bucket:
        - 'technical': coding, data structures, algorithms, SQL, system design,
          language/framework specifics, debugging, technical trade-offs, analytical
          case questions, data-analysis methodology.
        - 'behavioral': "tell me about a time...", teamwork, conflict, leadership,
          failure/learning stories, anything best answered with STAR.
        - 'hr_career': company fit, motivation, salary expectations,
          strengths/weaknesses, career goals, "why this role", general HR screening.

        Return ONLY the bucket name.""",
    }

    result = classifier_llm.invoke([system_msg] + history)
    return {"question_type": result.question_type}


def router(state: InterviewState):
    question_type = state.get("question_type", "hr_career")
    return {"next": question_type}


def technical_agent(state: InterviewState):
    history = _history_as_dicts(state["messages"])

    system_msg = {
        "role": "system",
        "content": """You are a senior engineer running a technical interview prep session.

            Before answering, scan the conversation history for ROLE CONTEXT the candidate
            has shared (e.g. "senior data analyst", "business data analyst", "backend",
            seniority, domain). Tailor depth, terminology, and example choices to that role.
            If the user has clarified or refined the role mid-conversation, the LATEST
            clarification wins.

            For the latest question, produce:
            1. A direct model answer. Use code/SQL/pseudocode when it sharpens the point.
               No throat-clearing. No "great question".
            2. Trade-offs that matter for this specific role (complexity, scalability,
               business impact, accuracy vs. latency — pick what's relevant, not all of them).
            3. Exactly 2 likely follow-ups the interviewer would ask next, written as
               questions the candidate should rehearse.

            Keep the whole response under ~350 words unless code requires more.""",
    }

    reply = llm.invoke([system_msg] + history)
    return {"messages": [{"role": "assistant", "content": reply.content}]}


def behavioral_agent(state: InterviewState):
    history = _history_as_dicts(state["messages"])

    system_msg = {
        "role": "system",
        "content": """You are a behavioral interview coach.

            Scan the conversation history for the role/seniority the candidate is
            targeting and tailor the example to that context (e.g. an IC story for a
            senior IC role, a cross-team-influence story for a lead role).

            For the latest behavioral question, produce:
            1. The SIGNAL the interviewer is actually probing for — one short line.
            2. A first-person model answer in STAR:
               - Situation (1-2 sentences)
               - Task (1 sentence)
               - Action (the bulk — what YOU specifically did, with concrete verbs)
               - Result (measurable outcome + 1 line of reflection)
            3. The single biggest pitfall to avoid on this question type.

            Keep it concrete. No hypotheticals, no "I would". Use plausible numbers.
            Under ~300 words.""",
    }

    reply = llm.invoke([system_msg] + history)
    return {"messages": [{"role": "assistant", "content": reply.content}]}


def hr_career_agent(state: InterviewState):
    history = _history_as_dicts(state["messages"])

    system_msg = {
        "role": "system",
        "content": """You are an HR / career interview coach.

            Scan the conversation history for the candidate's target role, level, and
            any company context they've shared. Tailor the model answer to that.

            For the latest HR-style or career-narrative question, produce:
            1. What the interviewer is REALLY evaluating — one short line.
            2. A model answer that is honest, confident, role-specific, and ties back
               to what the candidate has said about themselves earlier in the chat.
            3. One phrase to AVOID and why (cliché, red flag, or vague filler).

            Tight and professional. Under ~250 words.""",
    }

    reply = llm.invoke([system_msg] + history)
    return {"messages": [{"role": "assistant", "content": reply.content}]}


def coach_agent(state: InterviewState):
    latest_user_question = ""
    for msg in reversed(state["messages"]):
        if getattr(msg, "type", None) == "human":
            latest_user_question = msg.content
            break
    specialist_reply = state["messages"][-1].content if state["messages"] else ""

    messages = [
        {
            "role": "system",
            "content": """You are a delivery coach. A specialist has just produced a model answer
                to an interview question. Your job is to add 2-3 short bullets focused on
                *delivery*: pacing, tone, what signals to emphasize when saying this out loud,
                and common mistakes to avoid in the moment. Do NOT rewrite the answer.
                Keep it under 80 words. Start with the heading "Delivery tips:".""",
        },
        {
            "role": "user",
            "content": (
                f"Interview question:\n{latest_user_question}\n\n"
                f"Specialist's model answer:\n{specialist_reply}"
            ),
        },
    ]
    reply = llm.invoke(messages)
    return {"coach_tips": reply.content}


graph_builder = StateGraph(InterviewState)

graph_builder.add_node("classifier", classify_question)
graph_builder.add_node("router", router)
graph_builder.add_node("technical", technical_agent)
graph_builder.add_node("behavioral", behavioral_agent)
graph_builder.add_node("hr_career", hr_career_agent)
graph_builder.add_node("coach", coach_agent)

graph_builder.add_edge(START, "classifier")
graph_builder.add_edge("classifier", "router")

graph_builder.add_conditional_edges(
    "router",
    lambda state: state.get("next"),
    {
        "technical": "technical",
        "behavioral": "behavioral",
        "hr_career": "hr_career",
    },
)

graph_builder.add_edge("technical", "coach")
graph_builder.add_edge("behavioral", "coach")
graph_builder.add_edge("hr_career", "coach")
graph_builder.add_edge("coach", END)

graph = graph_builder.compile()


def run_interview_prep():
    state = {"messages": [], "question_type": None, "coach_tips": None}
    turn = 0

    while True:
        user_input = input("Interview question: ")
        if user_input == "exit":
            print("Bye")
            break

        turn += 1
        state["messages"] = state.get("messages", []) + [
            {"role": "user", "content": user_input}
        ]

        run_config: RunnableConfig = {
            "run_name": "interview-turn",
            "tags": ["interview-prep", "cli"],
            "metadata": {"surface": "cli", "turn": turn},
        }
        state = graph.invoke(state, config=run_config)

        messages = state.get("messages") or []
        if messages:
            specialist = messages[-1]
            print(f"\nSpecialist ({state.get('question_type')}):\n{specialist.content}\n")
        if state.get("coach_tips"):
            print(f"Coach:\n{state['coach_tips']}\n")


if __name__ == "__main__":
    run_interview_prep()