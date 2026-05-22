"""Typer CLI for the API server.

Exposed via ``[project.scripts]`` in ``pyproject.toml`` as the ``api`` command::

    uv run api dev      # hot-reload dev server on 127.0.0.1
    uv run api serve    # production server (configurable host/port/workers)
"""

from __future__ import annotations

import typer
import uvicorn

from api.config import settings

app = typer.Typer(
    name="api",
    help="Interview Prep API server CLI",
    no_args_is_help=True,
)


@app.command()
def dev(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind host"),
    port: int = typer.Option(settings.api_port, "--port", "-p", help="Bind port"),
):
    """Start the development API server with hot-reload."""
    uvicorn.run("api.main:app", host=host, port=port, reload=True, log_level="debug")


@app.command()
def serve(
    host: str = typer.Option(settings.api_host, "--host", "-h", help="Bind host"),
    port: int = typer.Option(settings.api_port, "--port", "-p", help="Bind port"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of worker processes"),
):
    """Start the production API server."""
    uvicorn.run("api.main:app", host=host, port=port, workers=workers, log_level="info")
