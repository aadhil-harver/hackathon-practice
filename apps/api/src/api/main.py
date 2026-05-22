"""FastAPI entry point. Builds the LangGraph at startup and serves it via REST + SSE."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.agent.graph import build_graph
from api.config import settings
from api.routers import interview_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the compiled graph once at startup and hang it on app.state.

    Persistence (Postgres checkpointer) is out of scope for the hackathon
    demo — see the Non-goals section in CLAUDE.md. Add it here when the
    scope changes.
    """
    logger.info("Building interview-prep graph…")
    app.state.graph = build_graph()
    logger.info("Graph ready")
    yield
    logger.info("Shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Interview Prep API",
        version="0.1.0",
        description="FastAPI + LangGraph multi-agent interview-prep backend",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(interview_router)

    @app.get("/api/health", tags=["health"])
    async def health():
        return {"status": "ok"}

    return app


app = create_app()