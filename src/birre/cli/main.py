"""CLI entry point."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from typer.main import get_command

from birre.cli.app import app

_CLI_PROG_NAME = "birre"


def main(argv: Sequence[str] | None = None) -> None:
    """Main entry point for BiRRe MCP server.

    Parameters
    ----------
    argv:
        Optional list of arguments to pass to Typer. When ``None`` the
        process arguments are used.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    command = get_command(app)

    # Default to 'run' command if no arguments provided
    if not args:
        command.main(args=["run"], prog_name=_CLI_PROG_NAME)
        return

    # Pass through help requests
    if args[0] in {"-h", "--help"}:
        command.main(args=args, prog_name=_CLI_PROG_NAME)
        return

    # If first arg is a flag, treat it as a run command option
    if args[0].startswith("-"):
        command.main(args=["run", *args], prog_name=_CLI_PROG_NAME)
    else:
        command.main(args=args, prog_name=_CLI_PROG_NAME)


__all__ = ["main"]
