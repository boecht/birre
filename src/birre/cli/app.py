"""BiRRe FastMCP server Typer CLI entrypoint."""

from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console
from rich.text import Text

# FastMCP checks this flag during import time, so ensure it is enabled before
# importing any modules that depend on FastMCP.
os.environ["FASTMCP_EXPERIMENTAL_ENABLE_NEW_OPENAPI_PARSER"] = "true"

from birre.application.diagnostics import (
    EXPECTED_TOOLS_BY_CONTEXT as _DIAGNOSTIC_EXPECTED_TOOLS,
)
from birre.cli.commands import config as config_command
from birre.cli.commands import logs as logs_command
from birre.cli.commands import run as run_command
from birre.cli.commands import selftest as selftest_command
from birre.integrations.bitsight import DEFAULT_V1_API_BASE_URL

PROJECT_ROOT = Path(__file__).resolve().parents[3]

stderr_console = Console(stderr=True)
stdout_console = Console(stderr=False)

app = typer.Typer(
    help="Model Context Protocol server for BitSight rating retrieval",
    rich_markup_mode="rich",
)


HEALTHCHECK_TESTING_V1_BASE_URL = "https://service.bitsighttech.com/customer-api/v1/"
HEALTHCHECK_PRODUCTION_V1_BASE_URL = DEFAULT_V1_API_BASE_URL

_EXPECTED_TOOLS_BY_CONTEXT: dict[str, frozenset[str]] = {
    context: frozenset(tools) for context, tools in _DIAGNOSTIC_EXPECTED_TOOLS.items()
}


# Banner functions for server startup -----------------------------------------


def _banner() -> Text:
    return Text.from_markup(
        "\n"
        "╭────────────────────────────────────────────────────────────────╮\n"
        "│[yellow]                                                                [/yellow]│\n"
        "│[yellow]     ███████████   ███  ███████████   ███████████               [/yellow]│\n"
        "│[yellow]    ░░███░░░░░███ ░░░  ░░███░░░░░███ ░░███░░░░░███              [/yellow]│\n"
        "│[yellow]     ░███    ░███ ████  ░███    ░███  ░███    ░███   ██████     [/yellow]│\n"
        "│[yellow]     ░██████████ ░░███  ░██████████   ░██████████   ███░░███    [/yellow]│\n"
        "│[yellow]     ░███░░░░░███ ░███  ░███░░░░░███  ░███░░░░░███ ░███████     [/yellow]│\n"
        "│[yellow]     ░███    ░███ ░███  ░███    ░███  ░███    ░███ ░███░░░      [/yellow]│\n"
        "│[yellow]     ███████████  █████ █████   █████ █████   █████░░██████     [/yellow]│\n"
        "│[yellow]    ░░░░░░░░░░░  ░░░░░ ░░░░░   ░░░░░ ░░░░░   ░░░░░  ░░░░░░      [/yellow]│\n"
        "│[yellow]                                                                [/yellow]│\n"
        "│[dim]                   "
        "[bold]Bi[/bold]tsight [bold]R[/bold]ating [bold]Re[/bold]triever"
        "                    [/dim]│\n"
        "│[yellow]                 Model Context Protocol Server                  [/yellow]│\n"
        "│[yellow]                https://github.com/boecht/birre                 [/yellow]│\n"
        "╰────────────────────────────────────────────────────────────────╯\n"
    )


def _keyboard_interrupt_banner() -> Text:
    return Text.from_markup(
        "\n"
        "╭───────────────────────────────╮\n"
        "│[red]  Keyboard interrupt received  [/red]│\n"
        "│[red]         BiRRe stopping        [/red]│\n"
        "╰───────────────────────────────╯\n"
    )


# Register extracted command modules (after dependencies are defined)
config_command.register(app, stdout_console=stdout_console)
logs_command.register(app, stdout_console=stdout_console)
run_command.register(
    app,
    stderr_console=stderr_console,
    banner_factory=_banner,
    keyboard_interrupt_banner=_keyboard_interrupt_banner,
)
selftest_command.register(
    app,
    stderr_console=stderr_console,
    stdout_console=stdout_console,
    banner_factory=_banner,
    expected_tools_by_context=_EXPECTED_TOOLS_BY_CONTEXT,
    healthcheck_testing_v1_base_url=HEALTHCHECK_TESTING_V1_BASE_URL,
    healthcheck_production_v1_base_url=HEALTHCHECK_PRODUCTION_V1_BASE_URL,
)


@app.command(help="Show the installed BiRRe package version.")
def version() -> None:
    """Print the BiRRe version discovered from the package metadata."""
    from importlib import metadata

    try:
        resolved_version = metadata.version("BiRRe")
    except metadata.PackageNotFoundError:
        pyproject = PROJECT_ROOT / "pyproject.toml"
        if not pyproject.exists():
            stdout_console.print("Version information unavailable")
            return
        import tomllib

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        resolved_version = data.get("project", {}).get("version", "unknown")
    stdout_console.print(resolved_version)


@app.command(help="Print the BiRRe README to standard output.")
def readme() -> None:
    """Display the project README for quick reference."""
    readme_path = PROJECT_ROOT / "README.md"
    if not readme_path.exists():
        raise typer.BadParameter("README.md not found in project root")
    stdout_console.print(readme_path.read_text(encoding="utf-8"))
