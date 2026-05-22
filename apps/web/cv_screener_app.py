"""Streamlit Recruiter Report UI for the CV-Screener graph.

This is the demo-ready surface (task #12). On top of the HITL Approve/Stop
flow built in task #11, it adds:

- A golden-path scenario dropdown that loads canned CV/JD pairs (Shortlist /
  Hold / Reject) so the live demo can replay every decision branch quickly.
- A structured Recruiter Report layout: colour-coded recommendation badge,
  score progress bars, side-by-side matched / missing skills, strengths /
  concerns, integrity flags, and per-question expandable interview cards.

Run with::

    uv run streamlit run apps/web/cv_screener_app.py
"""

from __future__ import annotations

import json

import streamlit as st
from langchain_core.runnables import RunnableConfig

from api.agent.cv_screening_graph import screening_graph
from api.agent.data.golden_paths import GOLDEN_PATHS, by_key
from api.agent.scoring import WEIGHTS
from api.export import default_filename, state_to_pdf
from api.extract import CVExtractionError, extract_text

st.set_page_config(
    page_title="CV Screener",
    page_icon="🧪",
    layout="wide",
)

# Harver-aligned brand tokens — used by avatar, profile chips, and skill pills.
# Recommendation badge colours (green/amber/red) stay semantic; everything else
# leans on this peach + neutral palette.
BRAND_PEACH = "#FF8B5E"
BRAND_PEACH_SOFT = "#FFE8DC"
BRAND_PEACH_BG = "#FFF7F2"
BRAND_INK = "#1A1A1A"
BRAND_INK_MUTED = "#5C5C5C"
BRAND_ACCENT_BLUE = "#378ADD"
BRAND_ACCENT_BLUE_SOFT = "#E6F1FB"

# Harver-style header — peach gradient stripe + title.
st.markdown(
    f"""
    <div style="
        background: linear-gradient(135deg, {BRAND_PEACH} 0%, #FFB380 60%, {BRAND_PEACH_SOFT} 100%);
        padding: 22px 28px; border-radius: 10px; margin-bottom: 18px;
        color: {BRAND_INK};">
        <div style="font-size:11px; letter-spacing:2px; opacity:0.85; font-weight:600;">
            CANDIDATE SCREENING WORKFLOW
        </div>
        <div style="font-size:28px; font-weight:700; margin-top:4px;">
            🧪&nbsp; CV-Screener
        </div>
        <div style="font-size:14px; max-width:780px; margin-top:6px; opacity:0.85;">
            Parses CV + JD, runs three assessment agents in parallel, integrity-checks
            the result, scores deterministically, and recommends
            <b>Shortlist</b> / <b>Hold</b> / <b>Reject</b>. Two human-in-the-loop
            confidence gates can pause the pipeline for recruiter approval.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ── Session state ─────────────────────────────────────────────────────────────

if "screening_state" not in st.session_state:
    st.session_state.screening_state = None
if "history" not in st.session_state:
    st.session_state.history = []
if "cv_input" not in st.session_state:
    st.session_state.cv_input = ""
if "jd_input" not in st.session_state:
    st.session_state.jd_input = ""
if "_last_cv_upload_id" not in st.session_state:
    # Identifier (name:size) of the last CV the uploader populated the textarea
    # with — lets us avoid re-extracting on every rerun and avoid clobbering
    # edits the user has made to the extracted text.
    st.session_state._last_cv_upload_id = None


# ── Helpers ───────────────────────────────────────────────────────────────────

REC_STYLE = {
    "Shortlist": ("✅", "#1D9E75", "Strong fit — move to interview."),
    "Hold": ("⏸️", "#BA7517", "Borderline — needs further review."),
    "Reject": ("⛔", "#D85A30", "Below threshold — do not advance."),
}

# Per-node display config — drives the live status panel during a run.
AGENT_DISPLAY = {
    "input_handler": ("📥", "Input handler"),
    "parser": ("🔎", "Parser"),
    "conf_gate_1": ("✋", "Gate #1"),
    "human_review_1": ("⚑", "Gate #1 — human review"),
    "skill_match": ("🔍", "Skill match"),
    "seniority": ("🎚️", "Seniority"),
    "experience": ("🧠", "Experience"),
    "integrity": ("🛡️", "Integrity & Fairness"),
    "conf_gate_2": ("✋", "Gate #2"),
    "human_review_2": ("⚑", "Gate #2 — human review"),
    "scorer": ("🧮", "Scorer (deterministic)"),
    "recommendation": ("⚖️", "Recommendation"),
    "interview_questions": ("🎯", "Interview questions"),
}

# LLM-backed nodes — used to distinguish "skipped because cached" from
# "no-op gate" (gates always return {} but are not cached).
_LLM_NODES = {"parser", "skill_match", "seniority", "experience", "integrity", "interview_questions"}
_GATE_NODES = {"conf_gate_1", "conf_gate_2"}
_PARALLEL_NODES = {"skill_match", "seniority", "experience"}

SUBSCORE_LABELS = {
    "skill_subscore": "Skills",
    "seniority_subscore": "Seniority",
    "domain_subscore": "Domain",
    "education_subscore": "Education",
}

WEIGHT_KEY_TO_SUBSCORE = {
    "skills": "skill_subscore",
    "seniority": "seniority_subscore",
    "domain": "domain_subscore",
    "education": "education_subscore",
}


def _format_node_line(node_name: str, update: dict | None) -> str:
    """Render one status row for the live panel, summarising the node's output."""
    emoji, label = AGENT_DISPLAY.get(node_name, ("🤖", node_name))
    update = update or {}

    # Gate nodes are no-op anchors — they always return {} regardless of caching.
    if node_name in _GATE_NODES:
        return f"{emoji} **{label}** — checking…"

    # LLM-backed nodes that returned {} got short-circuited by skip-if-cached.
    if node_name in _LLM_NODES and not update:
        return f"{emoji} **{label}** — _cached, skipped_"

    if node_name == "parser":
        conf = update.get("parse_confidence")
        if conf is not None:
            return f"{emoji} **{label}** → parse_confidence = `{conf:.2f}`"
    if node_name == "skill_match":
        m = len(update.get("matched_skills") or [])
        miss = len(update.get("missing_skills") or [])
        return f"{emoji} **{label}** → `{m}` matched · `{miss}` missing"
    if node_name == "seniority":
        s = update.get("assessed_seniority")
        return f"{emoji} **{label}** → `{s}`"
    if node_name == "experience":
        sc = len(update.get("strengths") or [])
        cc = len(update.get("concerns") or [])
        return f"{emoji} **{label}** → `{sc}` strengths · `{cc}` concerns"
    if node_name == "integrity":
        rc = update.get("risk_confidence")
        if rc is not None:
            return f"{emoji} **{label}** → risk_confidence = `{rc:.2f}`"
    if node_name == "scorer":
        sc = update.get("score")
        return f"{emoji} **{label}** → score = `{sc} / 10`"
    if node_name == "recommendation":
        rec = update.get("recommendation")
        return f"{emoji} **{label}** → **{rec}**"
    if node_name == "interview_questions":
        qs = len(update.get("questions") or [])
        return f"{emoji} **{label}** → `{qs}` questions generated"
    if node_name in ("human_review_1", "human_review_2"):
        gate = update.get("review_stage", "?")
        return f"{emoji} **{label}** — pipeline paused for review of `{gate}`"
    if node_name == "input_handler":
        return f"{emoji} **{label}** ✓"

    # Fallback for any future node not in the dispatch
    return f"{emoji} **{label}** ✓"


def _run_graph(graph_input: dict, label: str) -> dict:
    """Stream the graph, surface each agent as it fires, and return the final state.

    Uses ``stream_mode='updates'`` so we get a per-node update as soon as each
    node finishes — that's what makes the parallel fan-out visible. The three
    parallel agents emit in arbitrary order (whichever finishes first); they're
    all clearly tagged so the recruiter can see they ran concurrently.
    """
    config: RunnableConfig = {
        "run_name": "cv-screening-run",
        "tags": ["cv-screener", "streamlit", label],
        "metadata": {"surface": "streamlit", "label": label},
    }

    # We accumulate per-node updates into a single dict to reconstruct the
    # final state. ScreeningState has no reducer-based fields (every node writes
    # disjoint keys), so a plain merge is sound.
    result: dict = dict(graph_input)
    parallel_seen: list[str] = []
    failure_msg: str | None = None

    with st.status(f"Running graph ({label})…", expanded=True) as status:
        try:
            for chunk in screening_graph.stream(graph_input, config=config, stream_mode="updates"):
                for node_name, update in chunk.items():
                    if node_name in _PARALLEL_NODES:
                        parallel_seen.append(node_name)
                        order_tag = f" *(parallel {len(parallel_seen)}/3)*"
                    else:
                        order_tag = ""

                    line = _format_node_line(node_name, update) + order_tag
                    status.write(line)

                    if update:
                        result.update(update)
        except Exception as exc:  # noqa: BLE001 — we want to surface anything to the user
            # Don't crash the whole UI on a mid-pipeline failure. The most common
            # cause is an OpenRouter credit cap on the questions agent, in which
            # case the upstream score + recommendation are already in `result`
            # and the report below can still render meaningfully.
            failure_msg = str(exc)
            lower = failure_msg.lower()
            if "402" in failure_msg or "credit" in lower or "max_tokens" in lower:
                status.write(
                    "⚠️ **LLM credit / token cap hit** — pipeline stopped early. "
                    "Lower `QUESTIONS_MAX_TOKENS` in `.env` or top up OpenRouter credits."
                )
            else:
                status.write(f"❌ **Error**: `{failure_msg[:300]}`")

        stage = result.get("review_stage")
        if failure_msg:
            status.update(
                label="⚠️ Stopped early — see status panel",
                state="error",
                expanded=True,
            )
        elif stage:
            status.update(
                label=f"⚑ Paused at {stage} — recruiter review needed",
                state="error",
                expanded=True,
            )
        else:
            rec = result.get("recommendation") or "(no recommendation)"
            status.update(
                label=f"✅ Completed — recommendation: {rec}",
                state="complete",
                expanded=False,
            )

    return result


def _reset(*, keep_inputs: bool = False):
    st.session_state.screening_state = None
    st.session_state.history = []
    if not keep_inputs:
        st.session_state.cv_input = ""
        st.session_state.jd_input = ""
        st.session_state._last_cv_upload_id = None


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("Golden-path scenarios")
    st.caption("Load a canned CV/JD pair to demo one decision branch.")

    options = ["— pick a scenario —"] + [gp.label for gp in GOLDEN_PATHS]
    pick = st.selectbox("Scenario", options, label_visibility="collapsed")

    if pick != options[0]:
        gp = next(g for g in GOLDEN_PATHS if g.label == pick)
        if st.button(f"📥 Load: {gp.expected_recommendation} path", use_container_width=True):
            st.session_state.cv_input = gp.cv
            st.session_state.jd_input = gp.jd
            _reset(keep_inputs=True)
            st.rerun()
        st.info(gp.description, icon="ℹ️")
        st.caption(
            f"Expected: score in **{gp.expected_band}**, "
            f"recommendation = **{gp.expected_recommendation}**."
        )

    st.divider()
    st.subheader("Pipeline")
    st.markdown(
        "1. **Parsing** — CV + JD → structured profiles\n"
        "2. **Gate #1** — parse_confidence ≥ 0.6?\n"
        "3. **Skill / Seniority / Experience** *(parallel)*\n"
        "4. **Integrity & Fairness** — gaps · bias\n"
        "5. **Gate #2** — risk_confidence ≥ 0.6?\n"
        "6. **Scorer** — 40 / 30 / 20 / 10\n"
        "7. **Recommendation** — Shortlist / Hold / Reject\n"
        "8. **Questions** — skipped on Reject"
    )
    st.divider()
    if st.button("🧹 Reset", use_container_width=True):
        _reset()
        st.rerun()


# ── Input panel ───────────────────────────────────────────────────────────────

st.subheader("1 · Inputs")
left, right = st.columns(2)
with left:
    uploaded_cv = st.file_uploader(
        "Upload CV (PDF / DOCX / TXT)",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=False,
        help="Drop a candidate CV here. Text is extracted and shown below — "
        "edit if the extraction missed anything before running the screening.",
    )

    # Auto-extract on new upload. Skip re-extraction when the same file is
    # still in the uploader (avoids stomping user edits to the textarea).
    if uploaded_cv is not None:
        upload_id = f"{uploaded_cv.name}:{uploaded_cv.size}"
        if st.session_state._last_cv_upload_id != upload_id:
            try:
                extracted = extract_text(uploaded_cv)
                st.session_state.cv_input = extracted
                st.session_state._last_cv_upload_id = upload_id
                st.toast(
                    f"Extracted {len(extracted):,} chars from {uploaded_cv.name}",
                    icon="📄",
                )
            except CVExtractionError as e:
                st.error(f"Could not extract text from **{uploaded_cv.name}**: {e}")

    cv_text = st.text_area(
        "CV text",
        height=240,
        key="cv_input",
        placeholder="Paste the candidate CV here, upload a file above, "
        "or load a golden-path scenario from the sidebar…",
    )
with right:
    jd_text = st.text_area(
        "Job description",
        height=380,  # taller to align with the uploader + textarea on the left
        key="jd_input",
        placeholder="Paste the JD here…",
    )

submit = st.button("▶ Run screening", type="primary", disabled=not (cv_text and jd_text))

if submit:
    # Don't blow away the inputs — we keep them visible during/after the run
    st.session_state.screening_state = None
    st.session_state.history = [{"stage": "initial", "action": "submitted"}]
    st.session_state.screening_state = _run_graph(
        {"cv_text": cv_text, "jd_text": jd_text}, label="initial"
    )

state = st.session_state.screening_state


# ── HITL panels ───────────────────────────────────────────────────────────────


def _hitl_panel(*, gate: str, summary_section):
    st.warning(
        f"⚑ Pipeline paused at **{gate}**. Review the output below, then "
        "Approve to resume or Stop to reject this screening."
    )
    summary_section()

    cols = st.columns([1, 1, 4])
    approve = cols[0].button(f"✅ Approve {gate}", type="primary", key=f"approve_{gate}")
    stop = cols[1].button("🛑 Stop", key=f"stop_{gate}")

    if approve:
        flag_key = "force_pass_gate_1" if gate == "gate_1" else "force_pass_gate_2"
        resume_input = {**state, flag_key: True, "review_stage": None}
        st.session_state.screening_state = _run_graph(resume_input, label=f"resume-{gate}")
        st.session_state.history.append({"stage": gate, "action": "approved"})
        st.rerun()

    if stop:
        st.session_state.history.append({"stage": gate, "action": "stopped"})
        _reset(keep_inputs=True)
        st.info("Screening stopped by recruiter.")
        st.stop()


# ── Recruiter Report ──────────────────────────────────────────────────────────


def _initials(name: str | None) -> str:
    """Two-letter monogram for the avatar. Falls back to '??' when name is missing."""
    if not name:
        return "??"
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _render_candidate_profile(state_: dict):
    """Top-of-report profile block — avatar, name, subtitle, and three chips."""
    cv_profile = state_.get("cv_profile") or {}
    name = cv_profile.get("candidate_name") or "Candidate"
    current_role = cv_profile.get("current_role")
    years = cv_profile.get("years_experience")
    domains = cv_profile.get("domains") or []
    assessed_seniority = state_.get("assessed_seniority")

    # Profile header — avatar + name + subtitle
    col_avatar, col_name = st.columns([1, 9])
    with col_avatar:
        st.markdown(
            f"""
            <div style="
                background:{BRAND_PEACH}; color:white;
                width:64px; height:64px; border-radius:50%;
                display:flex; align-items:center; justify-content:center;
                font-size:22px; font-weight:600; margin-top:6px;
                box-shadow: 0 2px 8px rgba(255,139,94,0.25);">
                {_initials(name)}
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_name:
        st.markdown(f"### {name}")
        subtitle_parts: list[str] = []
        if current_role:
            subtitle_parts.append(current_role)
        if years is not None:
            subtitle_parts.append(f"{years} years")
        if domains:
            subtitle_parts.append(", ".join(domains[:2]))
        if subtitle_parts:
            st.caption(" · ".join(subtitle_parts))

    # Three chips — Seniority / Years / Domains
    c1, c2, c3 = st.columns(3)
    c1.metric("Seniority", (assessed_seniority or "—").title())
    c2.metric("Years", years if years is not None else "—")
    c3.metric("Domains", ", ".join(domains[:3]) if domains else "—")


def _render_recommendation_badge(score: int, recommendation: str):
    """Score + recommendation badge — two clean columns, no more 3-way fight for space."""
    emoji, colour, blurb = REC_STYLE.get(recommendation, ("❓", "#888888", ""))

    col_score, col_rec = st.columns([1, 3])
    col_score.metric("Score", f"{score} / 10")
    with col_rec:
        st.markdown(
            f"""
            <div style="
                background:{colour}; color:white;
                padding:18px 20px; border-radius:8px;
                font-size:20px; font-weight:600;
                display:flex; align-items:center; gap:10px;">
                <span style="font-size:28px;">{emoji}</span>
                <span>Recommendation: {recommendation}</span>
            </div>
            <p style="margin-top:8px; color:#666; font-size:13px;">{blurb}</p>
            """,
            unsafe_allow_html=True,
        )


def _render_score_breakdown(breakdown: dict):
    """4 progress bars, one per sub-score, with the weight as caption."""
    st.markdown("##### Score breakdown")
    cols = st.columns(4)
    for col, (weight_key, weight) in zip(cols, WEIGHTS.items()):
        subscore_key = WEIGHT_KEY_TO_SUBSCORE[weight_key]
        subscore = breakdown.get(subscore_key, 0.0)
        with col:
            st.markdown(f"**{SUBSCORE_LABELS[subscore_key]}**")
            st.progress(min(1.0, subscore / 10.0))
            st.caption(f"{subscore:.1f} / 10  ·  weight {int(weight * 100)}%")
    st.caption(f"Weighted raw: **{breakdown.get('weighted_raw', '—')}** → rounded to integer score.")


def _render_skills(matched: list[dict] | None, missing: list[str] | None):
    matched = matched or []
    missing = missing or []

    req_matches = [m for m in matched if m.get("kind") == "required"]
    nice_matches = [m for m in matched if m.get("kind") == "nice_to_have"]

    left, right = st.columns(2)
    with left:
        st.markdown("##### ✅ Matched skills")
        if req_matches:
            st.markdown(
                " ".join(
                    f"<span style='background:#E1F5EE;color:#085041;padding:3px 8px;"
                    f"border-radius:10px;margin:2px;display:inline-block;font-size:13px;'>"
                    f"{m['skill']}</span>"
                    for m in req_matches
                ),
                unsafe_allow_html=True,
            )
            st.caption(f"{len(req_matches)} required match(es)")
        else:
            st.caption("No required-skill matches.")

        if nice_matches:
            st.markdown(
                " ".join(
                    f"<span style='background:{BRAND_ACCENT_BLUE_SOFT};color:#0C447C;"
                    f"padding:3px 8px;border-radius:10px;margin:2px;"
                    f"display:inline-block;font-size:13px;'>"
                    f"{m['skill']} <em>(nice-to-have)</em></span>"
                    for m in nice_matches
                ),
                unsafe_allow_html=True,
            )

    with right:
        st.markdown("##### ⛔ Missing required skills")
        if missing:
            st.markdown(
                " ".join(
                    f"<span style='background:#FAECE7;color:#712B13;padding:3px 8px;"
                    f"border-radius:10px;margin:2px;display:inline-block;font-size:13px;'>"
                    f"{s}</span>"
                    for s in missing
                ),
                unsafe_allow_html=True,
            )
            st.caption(f"{len(missing)} missing")
        else:
            st.caption("None — candidate covers every required skill.")


def _render_strengths_concerns(strengths: list[str] | None, concerns: list[str] | None):
    left, right = st.columns(2)
    with left:
        st.markdown("##### 💪 Strengths")
        if strengths:
            for s in strengths:
                st.markdown(f"- {s}")
        else:
            st.caption("None surfaced.")
    with right:
        st.markdown("##### ⚠️ Concerns")
        if concerns:
            for c in concerns:
                st.markdown(f"- {c}")
        else:
            st.caption("None surfaced.")


def _render_integrity(state_: dict):
    gaps = state_.get("gaps") or []
    inconsistencies = state_.get("inconsistencies") or []
    bias_flags = state_.get("bias_flags") or []
    risk_conf = state_.get("risk_confidence")

    if not (gaps or inconsistencies or bias_flags):
        st.success(
            f"Integrity check clean — `risk_confidence = {risk_conf:.2f}`. "
            "No gaps, inconsistencies, or bias flags surfaced.",
            icon="🛡️",
        )
        return

    st.markdown(f"##### 🛡️ Integrity & Fairness  ·  risk_confidence = `{risk_conf:.2f}`")
    cols = st.columns(3)
    for col, label, items in (
        (cols[0], "Gaps", gaps),
        (cols[1], "Inconsistencies", inconsistencies),
        (cols[2], "Bias flags (recruiter awareness)", bias_flags),
    ):
        with col:
            st.markdown(f"**{label}**")
            if items:
                for it in items:
                    st.markdown(f"- {it}")
            else:
                st.caption("None")


def _render_questions(questions: list[dict] | None, recommendation: str):
    if not questions:
        if recommendation == "Reject":
            st.info("Interview questions skipped — recommendation is **Reject**.", icon="⛔")
        else:
            st.warning("No interview questions returned.")
        return

    st.markdown(f"##### 🎯 Interview questions ({len(questions)})")
    for i, q in enumerate(questions, 1):
        with st.expander(f"Q{i} · `{q.get('area', '?')}`  —  {q.get('question', '?')[:80]}…", expanded=False):
            st.markdown(f"**{q.get('question')}**")
            st.caption(f"Why asked: {q.get('why_asked')}")


def _render_report(state_: dict):
    """The full recruiter-facing report. Only rendered when the pipeline completed."""
    score = state_.get("score")
    rec = state_.get("recommendation")

    _render_candidate_profile(state_)
    st.divider()
    _render_recommendation_badge(score, rec)

    # PDF export — generated on demand. ReportLab is fast (<100ms for a typical
    # report), so we build it on every render rather than caching; this keeps
    # the bytes in sync with whatever the report currently shows.
    try:
        pdf_bytes = state_to_pdf(state_)
        st.download_button(
            "📄 Export report as PDF",
            data=pdf_bytes,
            file_name=default_filename(state_),
            mime="application/pdf",
            help="Download the entire Output section above as a PDF — "
            "score breakdown, skills, integrity flags, and interview questions.",
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"PDF export failed: {exc}")

    st.divider()

    breakdown = state_.get("score_breakdown")
    if breakdown:
        _render_score_breakdown(breakdown)
        st.divider()

    _render_skills(state_.get("matched_skills"), state_.get("missing_skills"))
    st.divider()

    _render_strengths_concerns(state_.get("strengths"), state_.get("concerns"))
    st.divider()

    _render_integrity(state_)
    st.divider()

    _render_questions(state_.get("questions"), rec)


# ── Result display ────────────────────────────────────────────────────────────

if state is not None:
    st.divider()
    st.subheader("2 · Output")

    review_stage = state.get("review_stage")

    if review_stage == "gate_1":

        def _summary_gate_1():
            st.metric("parse_confidence", f"{state.get('parse_confidence', 0):.2f}")
            st.caption("Threshold: 0.60 (below this, gate #1 pauses the pipeline)")
            with st.expander("Parsed CV profile", expanded=False):
                st.json(state.get("cv_profile"))
            with st.expander("Parsed JD profile", expanded=False):
                st.json(state.get("jd_profile"))

        _hitl_panel(gate="gate_1", summary_section=_summary_gate_1)

    elif review_stage == "gate_2":

        def _summary_gate_2():
            st.metric("risk_confidence", f"{state.get('risk_confidence', 0):.2f}")
            st.caption("Threshold: 0.60 (below this, gate #2 pauses for fairness review)")
            _render_integrity(state)

        _hitl_panel(gate="gate_2", summary_section=_summary_gate_2)

    elif state.get("score") is not None:
        _render_report(state)

    else:
        st.warning("Pipeline produced no score and no review stage. Check logs.")

    if st.session_state.history:
        with st.expander("Activity log", expanded=False):
            for entry in st.session_state.history:
                st.markdown(f"- **{entry['stage']}** — {entry['action']}")

    with st.expander("Raw state (debug)", expanded=False):
        st.code(
            json.dumps(
                {k: v for k, v in state.items() if not k.endswith("_text")},
                indent=2,
                default=str,
            )
        )
