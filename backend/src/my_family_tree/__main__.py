"""Entry point for `python -m my_family_tree`. Delegates to the CLI."""

from my_family_tree.cli.__main__ import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()
