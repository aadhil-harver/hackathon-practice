"""Render a CV-Screener result state to a PDF report (bytes).

Mirrors the Streamlit Recruiter Report layout — header with score + colour-coded
recommendation badge, score breakdown table, matched / missing skills,
strengths / concerns, integrity & fairness flags, and the interview questions.

Pure Python via ReportLab; no system deps. Designed to be called from the
Streamlit ``st.download_button`` but kept agnostic so a future FastAPI endpoint
can serve the same bytes.
"""

from __future__ import annotations

import io
from datetime import datetime
from html import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

REC_COLORS = {
    "Shortlist": colors.HexColor("#1D9E75"),
    "Hold": colors.HexColor("#BA7517"),
    "Reject": colors.HexColor("#D85A30"),
}

# Harver-aligned brand colours. The on-screen UI uses the same palette.
AVATAR_COLOR = colors.HexColor("#FF8B5E")
BRAND_PEACH_BG = colors.HexColor("#FFF7F2")


def _initials(name: str | None) -> str:
    if not name:
        return "??"
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _safe(text: object) -> str:
    """XML-escape text for Paragraph + strip characters Helvetica can't render."""
    s = "" if text is None else str(text)
    # ReportLab's Helvetica + WinAnsi covers most Western punctuation already.
    # We escape XML so user-supplied content can't break the flowable parser.
    return escape(s)


def _bullets(items: list[str] | None, body_style, empty_msg: str = "None") -> list:
    """Render a list of strings as a column of bulleted Paragraphs."""
    if not items:
        return [Paragraph(f"<i>{_safe(empty_msg)}</i>", body_style)]
    return [Paragraph(f"&bull;&nbsp; {_safe(it)}", body_style) for it in items]


def state_to_pdf(state: dict) -> bytes:
    """Build the recruiter-report PDF and return it as bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title="CV-Screening Report",
        author="CV-Screener",
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=22, spaceAfter=4)
    h3 = ParagraphStyle(
        "h3", parent=styles["Heading3"], fontSize=12, spaceBefore=10, spaceAfter=6
    )
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10, leading=14)
    caption = ParagraphStyle(
        "caption", parent=body, fontSize=9, textColor=colors.HexColor("#666666")
    )
    # Dedicated styles per badge cell — each picks its own font size, so we
    # don't rely on inline <font size='…'> tags that ReportLab's Paragraph
    # mis-measures and which were the cause of the overlap in the old layout.
    badge_label = ParagraphStyle(
        "badge_label", parent=body, fontSize=10, textColor=colors.white, leading=12
    )
    badge_value_big = ParagraphStyle(
        "badge_value_big",
        parent=body,
        fontSize=22,
        leading=26,
        textColor=colors.white,
        spaceBefore=2,
    )
    badge_value_med = ParagraphStyle(
        "badge_value_med",
        parent=body,
        fontSize=16,
        leading=20,
        textColor=colors.white,
        spaceBefore=2,
    )
    avatar_initials = ParagraphStyle(
        "avatar_initials",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=20,
        textColor=colors.white,
        alignment=1,  # center
    )
    name_style = ParagraphStyle(
        "name", parent=body, fontName="Helvetica-Bold", fontSize=18, leading=22
    )

    elements: list = []

    # ── Header ────────────────────────────────────────────────────────────
    elements.append(Paragraph("CV-Screening Report", h1))
    elements.append(
        Paragraph(
            f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            caption,
        )
    )
    elements.append(Spacer(1, 0.18 * inch))

    # ── Candidate profile (name, role, years, domains) ───────────────────
    cv_profile = state.get("cv_profile") or {}
    name = cv_profile.get("candidate_name") or "Candidate"
    current_role = cv_profile.get("current_role")
    years = cv_profile.get("years_experience")
    domains = cv_profile.get("domains") or []
    assessed = state.get("assessed_seniority") or "—"

    subtitle_parts: list[str] = []
    if current_role:
        subtitle_parts.append(_safe(current_role))
    if years is not None:
        subtitle_parts.append(f"{years} years")
    if domains:
        subtitle_parts.append(", ".join(_safe(d) for d in domains[:2]))
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else ""

    avatar_cell = Paragraph(_initials(name), avatar_initials)
    profile_text = [Paragraph(_safe(name), name_style)]
    if subtitle:
        profile_text.append(Paragraph(subtitle, caption))

    profile = Table(
        [[avatar_cell, profile_text]],
        colWidths=[0.65 * inch, 6.4 * inch],
        rowHeights=[0.65 * inch],
    )
    profile.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), AVATAR_COLOR),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (1, 0), (1, 0), 14),  # gap between avatar and text
            ]
        )
    )
    elements.append(profile)
    elements.append(Spacer(1, 0.15 * inch))

    # ── Profile chips: Seniority / Years / Domains ───────────────────────
    chip_label = ParagraphStyle(
        "chip_label",
        parent=body,
        fontSize=8,
        textColor=colors.HexColor("#666666"),
        leading=10,
    )
    chip_value = ParagraphStyle(
        "chip_value", parent=body, fontName="Helvetica-Bold", fontSize=12, leading=14
    )
    domains_str = ", ".join(_safe(d) for d in domains[:3]) if domains else "—"
    chips = Table(
        [
            [
                Paragraph("SENIORITY", chip_label),
                Paragraph("YEARS", chip_label),
                Paragraph("DOMAINS", chip_label),
            ],
            [
                Paragraph(_safe(assessed).title(), chip_value),
                Paragraph(_safe(years) if years is not None else "—", chip_value),
                Paragraph(domains_str, chip_value),
            ],
        ],
        colWidths=[2.35 * inch, 2.35 * inch, 2.35 * inch],
    )
    chips.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BRAND_PEACH_BG),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    elements.append(chips)
    elements.append(Spacer(1, 0.18 * inch))

    # ── Recommendation badge (score + recommendation, 2 cells) ────────────
    score = state.get("score")
    rec = state.get("recommendation") or "—"
    rec_color = REC_COLORS.get(rec, colors.grey)

    score_cell = [
        Paragraph("SCORE", badge_label),
        Paragraph(f"{_safe(score)} / 10", badge_value_big),
    ]
    rec_cell = [
        Paragraph("RECOMMENDATION", badge_label),
        Paragraph(_safe(rec).upper(), badge_value_med),
    ]

    badge = Table(
        [[score_cell, rec_cell]],
        colWidths=[2.2 * inch, 4.85 * inch],
    )
    badge.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), rec_color),
                ("LEFTPADDING", (0, 0), (-1, -1), 16),
                ("RIGHTPADDING", (0, 0), (-1, -1), 16),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    elements.append(badge)
    elements.append(Spacer(1, 0.2 * inch))

    # ── Score breakdown ───────────────────────────────────────────────────
    bd = state.get("score_breakdown") or {}
    if bd:
        elements.append(Paragraph("Score breakdown", h3))
        rows = [
            ["Component", "Sub-score", "Weight"],
            ["Skills", f"{bd.get('skill_subscore', 0):.1f} / 10", "40%"],
            ["Seniority", f"{bd.get('seniority_subscore', 0):.1f} / 10", "30%"],
            ["Domain", f"{bd.get('domain_subscore', 0):.1f} / 10", "20%"],
            ["Education", f"{bd.get('education_subscore', 0):.1f} / 10", "10%"],
        ]
        breakdown_table = Table(rows, colWidths=[2 * inch, 1.7 * inch, 1.2 * inch])
        breakdown_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BRAND_PEACH_BG),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                ]
            )
        )
        elements.append(breakdown_table)
        weighted_raw = bd.get("weighted_raw")
        if weighted_raw is not None:
            elements.append(
                Paragraph(
                    f"Weighted raw: <b>{weighted_raw}</b> &mdash; rounded to integer score.",
                    caption,
                )
            )

    # ── Skills ────────────────────────────────────────────────────────────
    matched = state.get("matched_skills") or []
    missing = state.get("missing_skills") or []
    elements.append(Paragraph("Matched skills", h3))
    if matched:
        for m in matched:
            elements.append(
                Paragraph(
                    f"&bull;&nbsp; {_safe(m.get('skill'))} "
                    f"<font color='#666666'><i>({_safe(m.get('kind'))})</i></font>",
                    body,
                )
            )
    else:
        elements.append(Paragraph("<i>No matched skills.</i>", body))

    elements.append(Paragraph("Missing required skills", h3))
    elements.extend(
        _bullets(
            missing,
            body,
            empty_msg="None — candidate covers every required skill.",
        )
    )

    # ── Strengths / Concerns ──────────────────────────────────────────────
    elements.append(Paragraph("Strengths", h3))
    elements.extend(_bullets(state.get("strengths"), body, "None surfaced."))

    elements.append(Paragraph("Concerns", h3))
    elements.extend(_bullets(state.get("concerns"), body, "None surfaced."))

    # ── Integrity & Fairness ──────────────────────────────────────────────
    risk_conf = state.get("risk_confidence")
    integrity_title = "Integrity & Fairness"
    if risk_conf is not None:
        integrity_title += f" (risk_confidence = {risk_conf:.2f})"
    elements.append(Paragraph(integrity_title, h3))

    for label, items in (
        ("Gaps", state.get("gaps")),
        ("Inconsistencies", state.get("inconsistencies")),
        ("Bias flags (recruiter awareness)", state.get("bias_flags")),
    ):
        elements.append(Paragraph(f"<b>{label}</b>", body))
        elements.extend(_bullets(items, body, "None"))
        elements.append(Spacer(1, 0.05 * inch))

    # ── Interview questions ───────────────────────────────────────────────
    questions = state.get("questions") or []
    elements.append(Paragraph(f"Interview questions ({len(questions)})", h3))
    if questions:
        for i, q in enumerate(questions, 1):
            block = [
                Paragraph(
                    f"<b>Q{i}.</b> <font color='#666666'><i>{_safe(q.get('area'))}</i></font>",
                    body,
                ),
                Paragraph(_safe(q.get("question")), body),
                Paragraph(
                    f"<i>Why asked: {_safe(q.get('why_asked'))}</i>", caption
                ),
                Spacer(1, 0.1 * inch),
            ]
            # KeepTogether stops a question from getting split across pages mid-block
            elements.append(KeepTogether(block))
    elif rec == "Reject":
        elements.append(
            Paragraph(
                "<i>Skipped — recommendation is Reject.</i>", body
            )
        )
    else:
        elements.append(Paragraph("<i>No interview questions returned.</i>", body))

    doc.build(elements)
    return buf.getvalue()


def default_filename(state: dict) -> str:
    """Produce a sensible default filename for the download button."""
    rec = (state.get("recommendation") or "report").lower()
    name = ((state.get("cv_profile") or {}).get("candidate_name") or "").strip()
    # Slug the name: keep alphanumerics, replace spaces with dashes
    name_slug = "-".join(p for p in name.lower().split() if p.isalnum()) if name else ""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    if name_slug:
        return f"cv-screening-{name_slug}-{rec}-{ts}.pdf"
    return f"cv-screening-{rec}-{ts}.pdf"
