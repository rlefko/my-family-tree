"""CLI entry point. Subcommands: version, mcp, worker, seed, tools."""

from __future__ import annotations

import asyncio
from typing import Annotated
from uuid import UUID

import typer

from my_family_tree import __version__

app = typer.Typer(
    name="mft",
    help="My Family Tree CLI.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _root() -> None:
    """Root callback ensures typer treats the app as a multi-command group."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def mcp(
    transport: Annotated[
        str,
        typer.Option("--transport", help="Transport: stdio or http (Streamable HTTP)."),
    ] = "stdio",
    host: Annotated[str, typer.Option("--host")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port")] = 8765,
    tree_id: Annotated[
        str | None,
        typer.Option(
            "--tree-id",
            help="Tree ID to scope to. Defaults to the all-zero UUID for v1 single-tree setups.",
        ),
    ] = None,
    capability: Annotated[
        str,
        typer.Option(
            "--capability",
            help=(
                "Comma-separated capabilities the server exposes "
                "(read, web, propose, trivial_write)."
            ),
        ),
    ] = "read",
    stateless: Annotated[
        bool,
        typer.Option(
            "--stateless/--stateful",
            help="Streamable HTTP only. Stateful (default) requires ALB sticky sessions.",
        ),
    ] = False,
) -> None:
    """Run the MCP server over stdio or Streamable HTTP."""
    from my_family_tree.core.config import get_settings
    from my_family_tree.core.logging import configure_logging
    from my_family_tree.db.session import make_engine, make_sessionmaker
    from my_family_tree.mcp.registry import Capability
    from my_family_tree.mcp.server import run_stdio, run_streamable_http

    settings = get_settings()
    configure_logging(level=settings.log_level, json_format=not settings.is_dev)

    engine = make_engine(settings)
    factory = make_sessionmaker(engine)
    resolved_tree = UUID(tree_id) if tree_id else UUID(int=0)

    cap_value = Capability(0)
    for name in (c.strip().lower() for c in capability.split(",") if c.strip()):
        try:
            cap_value |= Capability[name.upper()]
        except KeyError as e:
            raise typer.BadParameter(
                f"unknown capability {name!r}; expected one of: read, web, propose, trivial_write"
            ) from e
    if cap_value == Capability(0):
        cap_value = Capability.READ

    if transport == "stdio":
        asyncio.run(run_stdio(session_factory=factory, tree_id=resolved_tree, capability=cap_value))
    elif transport == "http":
        run_streamable_http(
            session_factory=factory,
            tree_id=resolved_tree,
            capability=cap_value,
            host=host,
            port=port,
            stateless=stateless,
        )
    else:
        raise typer.BadParameter(f"unknown transport {transport!r}; expected 'stdio' or 'http'")


@app.command()
def worker() -> None:
    """Run the arq worker. Equivalent to `arq my_family_tree.workers.arq_app.WorkerSettings`."""
    from arq import run_worker

    from my_family_tree.workers.arq_app import WorkerSettings

    run_worker(WorkerSettings)


@app.command()
def seed() -> None:
    """Load demo seed data. v1 stub."""
    from my_family_tree.cli.seed import run_seed

    asyncio.run(run_seed())


@app.command()
def tools() -> None:
    """Print the MCP tool catalog as JSON. Useful for verifying registry wiring."""
    from my_family_tree.mcp.server import _smoke

    _smoke()


if __name__ == "__main__":
    app()
