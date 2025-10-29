"""BiRRe FastMCP server Typer CLI entrypoint."""

from __future__ import annotations

import cProfile
import errno
import inspect
import json
import logging
import os
import re
import shutil
import ssl
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

import click
import httpx
import typer
from click.core import ParameterSource
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text
from typer.main import get_command


# FastMCP checks this flag during import time, so ensure it is enabled before
# importing any modules that depend on FastMCP.
os.environ["FASTMCP_EXPERIMENTAL_ENABLE_NEW_OPENAPI_PARSER"] = "true"

from birre.application.diagnostics import (
    EXPECTED_TOOLS_BY_CONTEXT as _DIAGNOSTIC_EXPECTED_TOOLS,
)
from birre.application.diagnostics import (
    DiagnosticFailure,
    HealthcheckRunner,
    aggregate_tool_outcomes,
    classify_failure,
    discover_context_tools,
    record_failure,
    run_company_search_diagnostics,
    run_company_search_interactive_diagnostics,
    run_context_tool_diagnostics,
    run_manage_subscriptions_diagnostics,
    run_rating_diagnostics,
    run_request_company_diagnostics,
    summarize_failure,
)

from birre.cli.helpers import (
    CONTEXT_CHOICES,
    await_sync,
    build_invocation,
    collect_tool_map,
    initialize_logging,
    prepare_server,
    resolve_runtime_and_logging,
    run_offline_checks,
    run_online_checks,
)
run_offline_startup_checks = run_offline_checks
run_online_startup_checks = run_online_checks

from birre.cli import options as cli_options
from birre.cli.commands import config as config_command
from birre.cli.commands import logs as logs_command
from birre.cli.commands import run as run_command
from birre.cli.commands import selftest as selftest_command
from birre.cli.models import (
    AuthOverrides,
    CliInvocation,
    LogViewLine,
    LoggingOverrides,
    RuntimeOverrides,
    SubscriptionOverrides,
    TlsOverrides,
)
from birre.config.constants import DEFAULT_CONFIG_FILENAME, LOCAL_CONFIG_FILENAME
from birre.config.settings import (
    BITSIGHT_API_KEY_KEY,
    BITSIGHT_SUBSCRIPTION_FOLDER_KEY,
    BITSIGHT_SUBSCRIPTION_TYPE_KEY,
    LOGGING_BACKUP_COUNT_KEY,
    LOGGING_FILE_KEY,
    LOGGING_FORMAT_KEY,
    LOGGING_LEVEL_KEY,
    LOGGING_MAX_BYTES_KEY,
    ROLE_CONTEXT_KEY,
    ROLE_MAX_FINDINGS_KEY,
    ROLE_RISK_VECTOR_FILTER_KEY,
    RUNTIME_ALLOW_INSECURE_TLS_KEY,
    RUNTIME_CA_BUNDLE_PATH_KEY,
    RUNTIME_DEBUG_KEY,
    RUNTIME_SKIP_STARTUP_CHECKS_KEY,
    LoggingInputs,
    RuntimeInputs,
    SubscriptionInputs,
    TlsInputs,
    apply_cli_overrides,
    is_logfile_disabled_value,
    load_settings,
    logging_from_settings,
    resolve_config_file_candidates,
    runtime_from_settings,
)
from birre.infrastructure.errors import (
    BirreError,
    ErrorCode,
)
from birre.infrastructure.logging import BoundLogger, configure_logging, get_logger
from birre.integrations.bitsight import DEFAULT_V1_API_BASE_URL

PROJECT_ROOT = Path(__file__).resolve().parents[3]

stderr_console = Console(stderr=True)
stdout_console = Console(stderr=False)

app = typer.Typer(
    help="Model Context Protocol server for BitSight rating retrieval",
    rich_markup_mode="rich",
)

class _RichStyles:
    ACCENT = "bold cyan"
    SECONDARY = "magenta"
    SUCCESS = "green"
    EMPHASIS = "bold"
    DETAIL = "white"


_CLI_PROG_NAME = Path(__file__).name
_SENSITIVE_KEY_PATTERNS = ("api_key", "secret", "token", "password")

SOURCE_USER_INPUT: Final = "User Input"

HEALTHCHECK_TESTING_V1_BASE_URL = "https://service.bitsighttech.com/customer-api/v1/"
HEALTHCHECK_PRODUCTION_V1_BASE_URL = DEFAULT_V1_API_BASE_URL

_HEALTHCHECK_COMPANY_NAME: Final = "GitHub"
_HEALTHCHECK_COMPANY_DOMAIN: Final = "github.com"
_HEALTHCHECK_COMPANY_GUID: Final = "6ca077e2-b5a7-42c2-ae1e-a974c3a91dc1"
_HEALTHCHECK_REQUEST_DOMAIN: Final = "healthcheck-birre-example.com"

# Error/status message constants
MSG_NOT_A_DICT: Final = "not a dict"
MSG_TOOL_INVOCATION_FAILED: Final = "tool invocation failed"
MSG_UNEXPECTED_PAYLOAD_STRUCTURE: Final = "unexpected payload structure"
MSG_EXPECTED_TOOL_NOT_REGISTERED: Final = "expected tool not registered"
MSG_TOOL_NOT_REGISTERED: Final = "tool not registered"
MSG_CONFIG_CA_BUNDLE: Final = "config.ca_bundle"

_EXPECTED_TOOLS_BY_CONTEXT: dict[str, frozenset[str]] = {
    context: frozenset(tools)
    for context, tools in _DIAGNOSTIC_EXPECTED_TOOLS.items()
}


# Reusable option annotations -------------------------------------------------

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


def main(argv: Sequence[str | None] = None) -> None:
    """Main entry point for BiRRe MCP server."""

    args = list(sys.argv[1:] if argv is None else argv)
    command = get_command(app)
    if not args:
        command.main(args=["run"], prog_name=_CLI_PROG_NAME)
        return

    if args[0] in {"-h", "--help"}:
        command.main(args=args, prog_name=_CLI_PROG_NAME)
        return

    if args[0].startswith("-"):
        command.main(args=["run", *args], prog_name=_CLI_PROG_NAME)
    else:
        command.main(args=args, prog_name=_CLI_PROG_NAME)


if __name__ == "__main__":
    main()
