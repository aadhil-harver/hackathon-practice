"""Sample job descriptions used by the golden-path demo scenarios.

Only one JD for now — Senior Backend Engineer at a fintech. The three sample
CVs in ``sample_cvs.py`` are all evaluated against this JD to exercise the
Shortlist / Hold / Reject branches of the deterministic scorer.
"""

from __future__ import annotations

SENIOR_BACKEND_FINTECH_JD = """Senior Backend Engineer — Fintech Payments Platform

About the role
We are looking for a Senior Backend Engineer with 6+ years of professional
experience to join our payments platform team. You will own the design and
implementation of high-throughput services that process millions of
transactions per day. You'll work end-to-end on services — from API design
through to operations — and mentor mid-level engineers on the team.

Required
- 6+ years of professional software engineering experience
- Strong Python (we're a Python-first backend shop)
- AWS at the application layer (Lambda, ECS, RDS, IAM)
- PostgreSQL — schema design, query tuning, migrations
- Docker for service packaging
- REST API design and implementation
- System design — you can lead a design review

Nice to have
- Kubernetes / production container orchestration
- Event-driven architectures (Kafka, Kinesis)
- Fintech / payments domain experience
- Experience mentoring or tech-leading

Domain
Payments / fintech. You will care about idempotency, consistency, and the
operational risks unique to handling money.
"""
