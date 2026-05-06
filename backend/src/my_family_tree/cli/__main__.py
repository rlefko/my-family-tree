"""CLI entry point. Subcommands: serve, mcp, worker, seed, version."""

from __future__ import annotations

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


# Other subcommands (serve, mcp, worker, seed) register themselves on this `app`
# in subsequent modules added in later commits.


if __name__ == "__main__":
    app()
