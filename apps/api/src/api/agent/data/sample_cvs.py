"""Three sample CVs that exercise every decision branch of the CV-Screener.

When run against ``SENIOR_BACKEND_FINTECH_JD`` they should produce:

- ``SENIOR_PYTHON_AWS_CV`` → score 8-10 → **Shortlist**
- ``MID_FRONTEND_CV``      → score 5-7  → **Hold**
- ``MARKETING_MANAGER_CV`` → score < 5  → **Reject** (interview questions skipped)

The scenarios double as the live-demo script (CLAUDE.md > Golden-path scenarios).
"""

from __future__ import annotations

SENIOR_PYTHON_AWS_CV = """Sarah Chen — Senior Software Engineer

Profile
8 years of professional software engineering experience. Senior IC focused
on backend systems for payments and fintech platforms. Comfortable owning
services from design through production operations, and have mentored
several mid-level engineers across two previous teams.

Skills
Python (FastAPI, Django), AWS (Lambda, ECS, RDS, IAM, Kinesis),
PostgreSQL, Docker, Kubernetes, REST APIs, gRPC, Kafka, Terraform,
GitHub Actions.

Experience

Senior Backend Engineer — PaymentsCo (2021 – present, 4 years)
- Owned the design and rollout of a card-tokenisation service handling
  ~12M transactions/day. Cut p95 latency from 240ms to 85ms.
- Led migration of the merchant settlement service from a monolithic Rails
  app to Python microservices on AWS ECS. 3 engineers reporting into the
  effort.
- Mentored 4 mid-level engineers; ran the team's design-review process.

Backend Engineer — HRTechCorp (2017 – 2021, 4 years)
- Built and operated a multi-tenant data platform ingesting 30M records/day
  for HR-tech SaaS customers.
- Designed the team's first event-driven pipeline (Kinesis + Lambda + DynamoDB)
  for real-time fraud detection on candidate-screening data.

Domains: fintech, payments, HR-tech.

Education
BSc Computer Science, University of Colombo (2017).
"""


MID_FRONTEND_CV = """Mark Rivera — Frontend Engineer

Profile
2 years of professional frontend engineering. Comfortable shipping React +
TypeScript features at a fast-growing e-commerce startup. Looking to grow
into more backend work — have shipped a handful of small Node.js APIs and
played with FastAPI on side projects.

Skills
JavaScript, TypeScript, React, Next.js, Node.js, Redux, Tailwind, REST API
consumption, Jest, Cypress, some Python (FastAPI side projects), Docker
(used in dev environments, not deeply).

Experience

Frontend Engineer — ShopRipe (2024 – present, 2 years)
- Built and shipped the product-detail page redesign — A/B test added
  4.1% to add-to-cart rate.
- Owned the checkout-flow rewrite from Redux to React Query.
- Built a small internal admin API in Node.js for the merchandising team.

Internship — ShopRipe (Summer 2023)
- Worked on the storefront search UI.

Domains: e-commerce.

Education
BSc Information Systems, University of Manchester (2023).
"""


MARKETING_MANAGER_CV = """Priya Desai — Marketing Manager

Profile
7 years of B2B SaaS marketing experience. Strong on demand generation,
content marketing, and managing agencies. Comfortable with Salesforce,
HubSpot, and the standard marketing analytics stack.

Skills
Salesforce, HubSpot, Marketo, Google Analytics, SQL (basic, for self-serve
dashboards), content strategy, paid acquisition, ABM, agency management,
event marketing.

Experience

Marketing Manager — CloudPay (2021 – present, 4 years)
- Built and led the demand-gen function from $0 to $4M influenced pipeline
  per quarter.
- Owned the relationship with two paid-acquisition agencies (~$1M/yr spend).
- Launched the company's first virtual conference (2000+ registrants).

Senior Marketing Specialist — DataNation (2018 – 2021)
- Ran content marketing across the BI product line.
- Owned the partnership-content programme with three integration partners.

Domains: B2B SaaS marketing, demand generation.

Education
MBA, INSEAD (2018). BA Communications, University of Mumbai (2014).
"""
