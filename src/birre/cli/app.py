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


def _create_offline_tool_status(tool_name: str, missing_set: set[str | None]) -> dict[str, Any]:
    """Create tool status entry for offline mode."""
    if tool_name in missing_set:
        return {
            "status": "fail",
            "details": {"reason": MSG_TOOL_NOT_REGISTERED},
        }
    return {
        "status": "warning",
        "details": {"reason": "offline mode"},
    }


def _collect_tool_attempts(
    tool_name: str, attempts: Sequence[dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Collect all attempt details and statuses for a specific tool."""
    attempt_details: dict[str, dict[str, Any]] = {}
    statuses: list[str] = []
    for attempt in attempts:
        tool_entry = attempt.get("tools", {}).get(tool_name)
        if tool_entry is None:
            continue
        attempt_details[attempt["label"]] = tool_entry
        status = tool_entry.get("status")
        if isinstance(status, str):
            statuses.append(status)
    return attempt_details, statuses


def _determine_final_status(statuses: list[str]) -> str:
    """Determine final tool status from multiple attempt statuses."""
    if any(status == "pass" for status in statuses):
        return "pass"
    if any(status == "fail" for status in statuses):
        return "fail"
    return statuses[0]


def _aggregate_tool_outcomes(
    expected_tools: frozenset[str],
    attempts: Sequence[dict[str, Any]],
    *,
    offline_mode: bool = False,
    offline_missing: Sequence[str | None] = None,
) -> dict[str, dict[str, Any]]:
    aggregated: dict[str, dict[str, Any]] = {}
    if offline_mode:
        missing_set = set(offline_missing or ())
        for tool_name in sorted(expected_tools):
            aggregated[tool_name] = _create_offline_tool_status(tool_name, missing_set)
        return aggregated

    for tool_name in sorted(expected_tools):
        attempt_details, statuses = _collect_tool_attempts(tool_name, attempts)
        
        if not statuses:
            aggregated[tool_name] = {
                "status": "warning",
                "attempts": attempt_details or None,
            }
            continue
        
        final_status = _determine_final_status(statuses)
        entry: dict[str, Any] = {"status": final_status}
        if attempt_details:
            entry["attempts"] = attempt_details
        aggregated[tool_name] = entry
    return aggregated


def _healthcheck_status_label(value: str | None) -> str:
    """Convert status value to uppercase label."""
    mapping = {"pass": "PASS", "fail": "FAIL", "warning": "WARNING"}
    if not value:
        return "WARNING"
    return mapping.get(value.lower(), value.upper())


def _stringify_healthcheck_detail(value: Any) -> str:
    """Convert any value to a string representation for healthcheck display."""
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        items = [f"{key}={value[key]}" for key in sorted(value)]
        return ", ".join(items) if items else "-"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = [_stringify_healthcheck_detail(item) for item in value]
        return ", ".join(item for item in items if item and item != "-") or "-"
    return str(value)


def _format_healthcheck_context_detail(context_data: Mapping[str, Any]) -> str:
    """Format context diagnostic details into a summary string."""
    parts: list[str] = []
    if context_data.get("fallback_attempted"):
        resolved = context_data.get("fallback_success")
        parts.append("fallback=" + ("resolved" if resolved else "failed"))
    recoverable = context_data.get("recoverable_categories") or []
    if recoverable:
        parts.append("recoverable=" + ",".join(sorted(recoverable)))
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        parts.append("unrecoverable=" + ",".join(sorted(unrecoverable)))
    notes = context_data.get("notes") or []
    if notes:
        parts.append("notes=" + ",".join(notes))
    return "; ".join(parts) if parts else "-"


def _format_healthcheck_online_detail(online_data: Mapping[str, Any]) -> str:
    """Format online diagnostic details into a summary string."""
    attempts = online_data.get("attempts") if isinstance(online_data, Mapping) else None
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = [
            f"{label}:{_healthcheck_status_label(status)}"
            for label, status in sorted(attempts.items())
        ]
        return ", ".join(attempt_parts)
    details = online_data.get("details") if isinstance(online_data, Mapping) else None
    return _stringify_healthcheck_detail(details)


def _process_tool_attempt_entry(
    label: str,
    entry: Mapping[str, Any],
    parts: list[str],
) -> str:
    """Process a single tool attempt entry and return its status label."""
    attempt_status = _healthcheck_status_label(entry.get("status"))
    
    modes = entry.get("modes")
    if isinstance(modes, Mapping) and modes:
        mode_parts = [
            f"{mode}:{_healthcheck_status_label(mode_entry.get('status'))}"
            for mode, mode_entry in sorted(modes.items())
        ]
        if mode_parts:
            parts.append(f"{label} modes=" + ", ".join(mode_parts))
    
    detail = entry.get("details")
    if detail:
        parts.append(f"{label} detail=" + _stringify_healthcheck_detail(detail))
    
    return f"{label}:{attempt_status}"


def _format_healthcheck_tool_detail(tool_summary: Mapping[str, Any]) -> str:
    """Format tool diagnostic details into a summary string."""
    parts: list[str] = []
    attempts = tool_summary.get("attempts")
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = []
        for label, entry in sorted(attempts.items()):
            attempt_label = _process_tool_attempt_entry(label, entry, parts)
            attempt_parts.append(attempt_label)
        if attempt_parts:
            parts.insert(0, "attempts=" + ", ".join(attempt_parts))
    
    details = tool_summary.get("details")
    if details:
        parts.append(_stringify_healthcheck_detail(details))
    
    return "; ".join(parts) if parts else "-"


def _create_healthcheck_table() -> Table:
    """Create the healthcheck summary table with columns."""
    table = Table(title="Healthcheck Summary", box=box.SIMPLE_HEAVY)
    table.add_column("Check", style=_RichStyles.ACCENT)
    table.add_column("Context", style=_RichStyles.SECONDARY)
    table.add_column("Tool", style=_RichStyles.SUCCESS)
    table.add_column("Status", style=_RichStyles.EMPHASIS)
    table.add_column("Details", style=_RichStyles.DETAIL)
    return table


def _add_healthcheck_offline_row(table: Table, report: dict[str, Any]) -> None:
    """Add the offline check row to the healthcheck table."""
    offline_entry = report.get("offline_check", {})
    offline_status = _healthcheck_status_label(offline_entry.get("status"))
    offline_detail = _stringify_healthcheck_detail(offline_entry.get("details"))
    table.add_row("Offline checks", "-", "-", offline_status, offline_detail)


def _determine_context_status(context_data: Mapping[str, Any]) -> str:
    """Determine the status label for a context."""
    context_success = context_data.get("success")
    offline_mode = context_data.get("offline_mode")
    if offline_mode and context_success:
        return "warning"
    elif context_success:
        return "pass"
    else:
        return "fail"


def _add_healthcheck_context_rows(
    table: Table,
    context_name: str,
    context_data: Mapping[str, Any],
) -> None:
    """Add context, online, and tool rows for a single context."""
    context_status = _determine_context_status(context_data)
    context_detail = _format_healthcheck_context_detail(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    table.add_row("Context", context_name, "-", context_status_label, context_detail)

    online_summary = context_data.get("online", {})
    online_status_label = _healthcheck_status_label(online_summary.get("status"))
    online_detail = _format_healthcheck_online_detail(online_summary)
    table.add_row("Online", context_name, "-", online_status_label, online_detail or "-")

    tools = context_data.get("tools", {})
    for tool_name, tool_summary in sorted(tools.items()):
        tool_status_label = _healthcheck_status_label(tool_summary.get("status"))
        detail_text = _format_healthcheck_tool_detail(tool_summary)
        table.add_row("Tool", context_name, tool_name, tool_status_label, detail_text)


def _collect_healthcheck_critical_failures(
    context_name: str,
    context_data: Mapping[str, Any],
) -> list[str]:
    """Collect critical failure messages for a context."""
    failures: list[str] = []
    context_status = _determine_context_status(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    
    if context_status_label == "FAIL":
        failures.append(f"{context_name}: context failure")
    
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        failures.append(
            f"{context_name}: unrecoverable={','.join(sorted(unrecoverable))}"
        )
    
    return failures


def _render_healthcheck_summary(report: dict[str, Any]) -> None:
    """Render a comprehensive healthcheck summary table and JSON report."""
    table = _create_healthcheck_table()
    _add_healthcheck_offline_row(table, report)

    critical_failures: list[str] = []
    for context_name, context_data in sorted(report.get("contexts", {}).items()):
        _add_healthcheck_context_rows(table, context_name, context_data)
        critical_failures.extend(
            _collect_healthcheck_critical_failures(context_name, context_data)
        )

    if critical_failures:
        table.add_row(
            "Critical failures",
            "-",
            "-",
            "FAIL",
            "; ".join(critical_failures),
        )

    stdout_console.print()
    stdout_console.print(table)
    stdout_console.print()
    stdout_console.print("Machine-readable summary:")
    stdout_console.print(json.dumps(report, indent=2, sort_keys=True))


def _format_exception_message(exc: BaseException) -> str:
    return str(exc)


def _validate_company_entry(entry: Any, logger: BoundLogger) -> bool:
    """Validate a single company entry in search results."""
    if not isinstance(entry, dict):
        logger.critical("healthcheck.company_search.invalid_company", reason="entry not dict")
        return False
    if not entry.get("guid") or not entry.get("name"):
        logger.critical(
            "healthcheck.company_search.invalid_company",
            reason="missing guid/name",
            company=entry,
        )
        return False
    return True


def _check_domain_match(companies: list, expected_domain: str, logger: BoundLogger) -> bool:
    """Check if expected domain is present in company list."""
    for entry in companies:
        domain_value = str(entry.get("domain") or "")
        if domain_value.lower() == expected_domain.lower():
            return True
    logger.critical("healthcheck.company_search.domain_missing", expected=expected_domain)
    return False


def _validate_company_search_payload(
    payload: Any,
    *,
    logger: BoundLogger,
    expected_domain: str | None = None,
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.company_search.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.company_search.api_error", error=str(payload["error"]))
        return False

    companies = payload.get("companies")
    if not isinstance(companies, list) or not companies:
        logger.critical("healthcheck.company_search.empty", reason="no companies returned")
        return False

    for entry in companies:
        if not _validate_company_entry(entry, logger):
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical("healthcheck.company_search.invalid_count", count=count_value)
        return False

    if expected_domain and not _check_domain_match(companies, expected_domain, logger):
        return False

    return True


def _validate_rating_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.rating.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.rating.api_error", error=str(payload["error"]))
        return False

    required_fields = ("name", "domain", "current_rating", "top_findings", "legend")
    for field in required_fields:
        if payload.get(field) in (None, {}):
            logger.critical("healthcheck.rating.missing_field", field=field)
            return False

    current_rating = payload.get("current_rating")
    if not isinstance(current_rating, dict) or current_rating.get("value") is None:
        logger.critical("healthcheck.rating.invalid_current_rating", payload=current_rating)
        return False

    findings = payload.get("top_findings")
    if not isinstance(findings, dict):
        logger.critical("healthcheck.rating.invalid_findings", payload=findings)
        return False

    finding_count = findings.get("count")
    finding_entries = findings.get("findings")
    if not isinstance(finding_count, int) or finding_count <= 0:
        logger.critical("healthcheck.rating.no_findings", count=finding_count)
        return False
    if not isinstance(finding_entries, list) or not finding_entries:
        logger.critical("healthcheck.rating.empty_findings", payload=findings)
        return False

    legend = payload.get("legend")
    if not isinstance(legend, dict) or not legend.get("rating"):
        logger.critical("healthcheck.rating.missing_legend", payload=legend)
        return False

    return True


def _validate_company_search_interactive_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical(
            "healthcheck.company_search_interactive.invalid_response", reason=MSG_NOT_A_DICT
        )
        return False

    if payload.get("error"):
        logger.critical(
            "healthcheck.company_search_interactive.api_error",
            error=str(payload["error"]),
        )
        return False

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        logger.critical(
            "healthcheck.company_search_interactive.empty_results",
            reason="no interactive results",
        )
        return False

    for entry in results:
        if not isinstance(entry, dict):
            logger.critical(
                "healthcheck.company_search_interactive.invalid_entry",
                reason="entry not dict",
            )
            return False
        required_keys = ("guid", "name", "primary_domain", "subscription")
        if any(not entry.get(key) for key in required_keys):
            logger.critical(
                "healthcheck.company_search_interactive.missing_fields",
                entry=entry,
            )
            return False
        subscription = entry.get("subscription")
        if not isinstance(subscription, dict) or "active" not in subscription:
            logger.critical(
                "healthcheck.company_search_interactive.invalid_subscription",
                subscription=subscription,
            )
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical(
            "healthcheck.company_search_interactive.invalid_count",
            count=count_value,
        )
        return False

    guidance = payload.get("guidance")
    if not isinstance(guidance, dict):
        logger.critical("healthcheck.company_search_interactive.missing_guidance")
        return False

    return True


def _validate_manage_subscriptions_payload(
    payload: Any, *, logger: BoundLogger, expected_guid: str
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.manage_subscriptions.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.manage_subscriptions.api_error", error=str(payload["error"]))
        return False

    status = payload.get("status")
    if status not in {"dry_run", "applied"}:
        logger.critical("healthcheck.manage_subscriptions.unexpected_status", status=status)
        return False

    guids = payload.get("guids")
    if not isinstance(guids, list) or expected_guid not in guids:
        logger.critical(
            "healthcheck.manage_subscriptions.guid_missing",
            guids=guids,
            expected=expected_guid,
        )
        return False

    if status == "dry_run":
        dry_payload = payload.get("payload")
        if not isinstance(dry_payload, dict) or "add" not in dry_payload:
            logger.critical(
                "healthcheck.manage_subscriptions.invalid_payload",
                payload=dry_payload,
            )
            return False

    return True


def _healthcheck_status_label(value: str | None) -> str:
    """Convert status value to uppercase label."""
    mapping = {"pass": "PASS", "fail": "FAIL", "warning": "WARNING"}
    if not value:
        return "WARNING"
    return mapping.get(value.lower(), value.upper())


def _stringify_healthcheck_detail(value: Any) -> str:
    """Convert any value to a string representation for healthcheck display."""
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        items = [f"{key}={value[key]}" for key in sorted(value)]
        return ", ".join(items) if items else "-"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = [_stringify_healthcheck_detail(item) for item in value]
        return ", ".join(item for item in items if item and item != "-") or "-"
    return str(value)


def _format_healthcheck_context_detail(context_data: Mapping[str, Any]) -> str:
    """Format context diagnostic details into a summary string."""
    parts: list[str] = []
    if context_data.get("fallback_attempted"):
        resolved = context_data.get("fallback_success")
        parts.append("fallback=" + ("resolved" if resolved else "failed"))
    recoverable = context_data.get("recoverable_categories") or []
    if recoverable:
        parts.append("recoverable=" + ",".join(sorted(recoverable)))
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        parts.append("unrecoverable=" + ",".join(sorted(unrecoverable)))
    notes = context_data.get("notes") or []
    if notes:
        parts.append("notes=" + ",".join(notes))
    return "; ".join(parts) if parts else "-"


def _format_healthcheck_online_detail(online_data: Mapping[str, Any]) -> str:
    """Format online diagnostic details into a summary string."""
    attempts = online_data.get("attempts") if isinstance(online_data, Mapping) else None
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = [
            f"{label}:{_healthcheck_status_label(status)}"
            for label, status in sorted(attempts.items())
        ]
        return ", ".join(attempt_parts)
    details = online_data.get("details") if isinstance(online_data, Mapping) else None
    return _stringify_healthcheck_detail(details)


def _process_tool_attempt_entry(
    label: str,
    entry: Mapping[str, Any],
    parts: list[str],
) -> str:
    """Process a single tool attempt entry and return its status label."""
    attempt_status = _healthcheck_status_label(entry.get("status"))
    
    modes = entry.get("modes")
    if isinstance(modes, Mapping) and modes:
        mode_parts = [
            f"{mode}:{_healthcheck_status_label(mode_entry.get('status'))}"
            for mode, mode_entry in sorted(modes.items())
        ]
        if mode_parts:
            parts.append(f"{label} modes=" + ", ".join(mode_parts))
    
    detail = entry.get("details")
    if detail:
        parts.append(f"{label} detail=" + _stringify_healthcheck_detail(detail))
    
    return f"{label}:{attempt_status}"


def _format_healthcheck_tool_detail(tool_summary: Mapping[str, Any]) -> str:
    """Format tool diagnostic details into a summary string."""
    parts: list[str] = []
    attempts = tool_summary.get("attempts")
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = []
        for label, entry in sorted(attempts.items()):
            attempt_label = _process_tool_attempt_entry(label, entry, parts)
            attempt_parts.append(attempt_label)
        if attempt_parts:
            parts.insert(0, "attempts=" + ", ".join(attempt_parts))
    
    details = tool_summary.get("details")
    if details:
        parts.append(_stringify_healthcheck_detail(details))
    
    return "; ".join(parts) if parts else "-"


def _create_healthcheck_table() -> Table:
    """Create the healthcheck summary table with columns."""
    table = Table(title="Healthcheck Summary", box=box.SIMPLE_HEAVY)
    table.add_column("Check", style=_RichStyles.ACCENT)
    table.add_column("Context", style=_RichStyles.SECONDARY)
    table.add_column("Tool", style=_RichStyles.SUCCESS)
    table.add_column("Status", style=_RichStyles.EMPHASIS)
    table.add_column("Details", style=_RichStyles.DETAIL)
    return table


def _add_healthcheck_offline_row(table: Table, report: dict[str, Any]) -> None:
    """Add the offline check row to the healthcheck table."""
    offline_entry = report.get("offline_check", {})
    offline_status = _healthcheck_status_label(offline_entry.get("status"))
    offline_detail = _stringify_healthcheck_detail(offline_entry.get("details"))
    table.add_row("Offline checks", "-", "-", offline_status, offline_detail)


def _determine_context_status(context_data: Mapping[str, Any]) -> str:
    """Determine the status label for a context."""
    context_success = context_data.get("success")
    offline_mode = context_data.get("offline_mode")
    if offline_mode and context_success:
        return "warning"
    elif context_success:
        return "pass"
    else:
        return "fail"


def _add_healthcheck_context_rows(
    table: Table,
    context_name: str,
    context_data: Mapping[str, Any],
) -> None:
    """Add context, online, and tool rows for a single context."""
    context_status = _determine_context_status(context_data)
    context_detail = _format_healthcheck_context_detail(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    table.add_row("Context", context_name, "-", context_status_label, context_detail)

    online_summary = context_data.get("online", {})
    online_status_label = _healthcheck_status_label(online_summary.get("status"))
    online_detail = _format_healthcheck_online_detail(online_summary)
    table.add_row("Online", context_name, "-", online_status_label, online_detail or "-")

    tools = context_data.get("tools", {})
    for tool_name, tool_summary in sorted(tools.items()):
        tool_status_label = _healthcheck_status_label(tool_summary.get("status"))
        detail_text = _format_healthcheck_tool_detail(tool_summary)
        table.add_row("Tool", context_name, tool_name, tool_status_label, detail_text)


def _collect_healthcheck_critical_failures(
    context_name: str,
    context_data: Mapping[str, Any],
) -> list[str]:
    """Collect critical failure messages for a context."""
    failures: list[str] = []
    context_status = _determine_context_status(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    
    if context_status_label == "FAIL":
        failures.append(f"{context_name}: context failure")
    
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        failures.append(
            f"{context_name}: unrecoverable={','.join(sorted(unrecoverable))}"
        )
    
    return failures


def _render_healthcheck_summary(report: dict[str, Any]) -> None:
    """Render a comprehensive healthcheck summary table and JSON report."""
    table = _create_healthcheck_table()
    _add_healthcheck_offline_row(table, report)

    critical_failures: list[str] = []
    for context_name, context_data in sorted(report.get("contexts", {}).items()):
        _add_healthcheck_context_rows(table, context_name, context_data)
        critical_failures.extend(
            _collect_healthcheck_critical_failures(context_name, context_data)
        )

    if critical_failures:
        table.add_row(
            "Critical failures",
            "-",
            "-",
            "FAIL",
            "; ".join(critical_failures),
        )

    stdout_console.print()
    stdout_console.print(table)
    stdout_console.print()
    stdout_console.print("Machine-readable summary:")
    stdout_console.print(json.dumps(report, indent=2, sort_keys=True))


def _format_exception_message(exc: BaseException) -> str:
    return str(exc)


def _validate_company_entry(entry: Any, logger: BoundLogger) -> bool:
    """Validate a single company entry in search results."""
    if not isinstance(entry, dict):
        logger.critical("healthcheck.company_search.invalid_company", reason="entry not dict")
        return False
    if not entry.get("guid") or not entry.get("name"):
        logger.critical(
            "healthcheck.company_search.invalid_company",
            reason="missing guid/name",
            company=entry,
        )
        return False
    return True


def _check_domain_match(companies: list, expected_domain: str, logger: BoundLogger) -> bool:
    """Check if expected domain is present in company list."""
    for entry in companies:
        domain_value = str(entry.get("domain") or "")
        if domain_value.lower() == expected_domain.lower():
            return True
    logger.critical("healthcheck.company_search.domain_missing", expected=expected_domain)
    return False


def _validate_company_search_payload(
    payload: Any,
    *,
    logger: BoundLogger,
    expected_domain: str | None = None,
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.company_search.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.company_search.api_error", error=str(payload["error"]))
        return False

    companies = payload.get("companies")
    if not isinstance(companies, list) or not companies:
        logger.critical("healthcheck.company_search.empty", reason="no companies returned")
        return False

    for entry in companies:
        if not _validate_company_entry(entry, logger):
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical("healthcheck.company_search.invalid_count", count=count_value)
        return False

    if expected_domain and not _check_domain_match(companies, expected_domain, logger):
        return False

    return True


def _validate_rating_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.rating.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.rating.api_error", error=str(payload["error"]))
        return False

    required_fields = ("name", "domain", "current_rating", "top_findings", "legend")
    for field in required_fields:
        if payload.get(field) in (None, {}):
            logger.critical("healthcheck.rating.missing_field", field=field)
            return False

    current_rating = payload.get("current_rating")
    if not isinstance(current_rating, dict) or current_rating.get("value") is None:
        logger.critical("healthcheck.rating.invalid_current_rating", payload=current_rating)
        return False

    findings = payload.get("top_findings")
    if not isinstance(findings, dict):
        logger.critical("healthcheck.rating.invalid_findings", payload=findings)
        return False

    finding_count = findings.get("count")
    finding_entries = findings.get("findings")
    if not isinstance(finding_count, int) or finding_count <= 0:
        logger.critical("healthcheck.rating.no_findings", count=finding_count)
        return False
    if not isinstance(finding_entries, list) or not finding_entries:
        logger.critical("healthcheck.rating.empty_findings", payload=findings)
        return False

    legend = payload.get("legend")
    if not isinstance(legend, dict) or not legend.get("rating"):
        logger.critical("healthcheck.rating.missing_legend", payload=legend)
        return False

    return True


def _validate_company_search_interactive_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical(
            "healthcheck.company_search_interactive.invalid_response", reason=MSG_NOT_A_DICT
        )
        return False

    if payload.get("error"):
        logger.critical(
            "healthcheck.company_search_interactive.api_error",
            error=str(payload["error"]),
        )
        return False

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        logger.critical(
            "healthcheck.company_search_interactive.empty_results",
            reason="no interactive results",
        )
        return False

    for entry in results:
        if not isinstance(entry, dict):
            logger.critical(
                "healthcheck.company_search_interactive.invalid_entry",
                reason="entry not dict",
            )
            return False
        required_keys = ("guid", "name", "primary_domain", "subscription")
        if any(not entry.get(key) for key in required_keys):
            logger.critical(
                "healthcheck.company_search_interactive.missing_fields",
                entry=entry,
            )
            return False
        subscription = entry.get("subscription")
        if not isinstance(subscription, dict) or "active" not in subscription:
            logger.critical(
                "healthcheck.company_search_interactive.invalid_subscription",
                subscription=subscription,
            )
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical(
            "healthcheck.company_search_interactive.invalid_count",
            count=count_value,
        )
        return False

    guidance = payload.get("guidance")
    if not isinstance(guidance, dict):
        logger.critical("healthcheck.company_search_interactive.missing_guidance")
        return False

    return True


def _validate_manage_subscriptions_payload(
    payload: Any, *, logger: BoundLogger, expected_guid: str
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.manage_subscriptions.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.manage_subscriptions.api_error", error=str(payload["error"]))
        return False

    status = payload.get("status")
    if status not in {"dry_run", "applied"}:
        logger.critical("healthcheck.manage_subscriptions.unexpected_status", status=status)
        return False

    guids = payload.get("guids")
    if not isinstance(guids, list) or expected_guid not in guids:
        logger.critical(
            "healthcheck.manage_subscriptions.guid_missing",
            guids=guids,
            expected=expected_guid,
        )
        return False

    if status == "dry_run":
        dry_payload = payload.get("payload")
        if not isinstance(dry_payload, dict) or "add" not in dry_payload:
            logger.critical(
                "healthcheck.manage_subscriptions.invalid_payload",
                payload=dry_payload,
            )
            return False

    return True


def _validate_request_company_payload(
    payload: Any, *, logger: BoundLogger, expected_domain: str
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.request_company.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.request_company.api_error", error=str(payload["error"]))
        return False

    status = payload.get("status")
    if status not in {"dry_run", "already_requested"}:
        logger.critical("healthcheck.request_company.unexpected_status", status=status)
        return False

    domain_value = payload.get("domain")
    if not isinstance(domain_value, str) or domain_value.lower() != expected_domain.lower():
        logger.critical(
            "healthcheck.request_company.domain_mismatch",
            domain=domain_value,
            expected=expected_domain,
        )
        return False

    if status == "dry_run":
        dry_payload = payload.get("payload")
        if not isinstance(dry_payload, dict) or "file" not in dry_payload:
            logger.critical("healthcheck.request_company.invalid_payload", payload=dry_payload)
            return False
    else:
        requests = payload.get("requests")
        if not isinstance(requests, list):
            logger.critical(
                "healthcheck.request_company.invalid_requests",
                requests=requests,
            )
            return False

    return True


def _healthcheck_status_label(value: str | None) -> str:
    """Convert status value to uppercase label."""
    mapping = {"pass": "PASS", "fail": "FAIL", "warning": "WARNING"}
    if not value:
        return "WARNING"
    return mapping.get(value.lower(), value.upper())


def _stringify_healthcheck_detail(value: Any) -> str:
    """Convert any value to a string representation for healthcheck display."""
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        items = [f"{key}={value[key]}" for key in sorted(value)]
        return ", ".join(items) if items else "-"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = [_stringify_healthcheck_detail(item) for item in value]
        return ", ".join(item for item in items if item and item != "-") or "-"
    return str(value)


def _format_healthcheck_context_detail(context_data: Mapping[str, Any]) -> str:
    """Format context diagnostic details into a summary string."""
    parts: list[str] = []
    if context_data.get("fallback_attempted"):
        resolved = context_data.get("fallback_success")
        parts.append("fallback=" + ("resolved" if resolved else "failed"))
    recoverable = context_data.get("recoverable_categories") or []
    if recoverable:
        parts.append("recoverable=" + ",".join(sorted(recoverable)))
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        parts.append("unrecoverable=" + ",".join(sorted(unrecoverable)))
    notes = context_data.get("notes") or []
    if notes:
        parts.append("notes=" + ",".join(notes))
    return "; ".join(parts) if parts else "-"


def _format_healthcheck_online_detail(online_data: Mapping[str, Any]) -> str:
    """Format online diagnostic details into a summary string."""
    attempts = online_data.get("attempts") if isinstance(online_data, Mapping) else None
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = [
            f"{label}:{_healthcheck_status_label(status)}"
            for label, status in sorted(attempts.items())
        ]
        return ", ".join(attempt_parts)
    details = online_data.get("details") if isinstance(online_data, Mapping) else None
    return _stringify_healthcheck_detail(details)


def _process_tool_attempt_entry(
    label: str,
    entry: Mapping[str, Any],
    parts: list[str],
) -> str:
    """Process a single tool attempt entry and return its status label."""
    attempt_status = _healthcheck_status_label(entry.get("status"))
    
    modes = entry.get("modes")
    if isinstance(modes, Mapping) and modes:
        mode_parts = [
            f"{mode}:{_healthcheck_status_label(mode_entry.get('status'))}"
            for mode, mode_entry in sorted(modes.items())
        ]
        if mode_parts:
            parts.append(f"{label} modes=" + ", ".join(mode_parts))
    
    detail = entry.get("details")
    if detail:
        parts.append(f"{label} detail=" + _stringify_healthcheck_detail(detail))
    
    return f"{label}:{attempt_status}"


def _format_healthcheck_tool_detail(tool_summary: Mapping[str, Any]) -> str:
    """Format tool diagnostic details into a summary string."""
    parts: list[str] = []
    attempts = tool_summary.get("attempts")
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = []
        for label, entry in sorted(attempts.items()):
            attempt_label = _process_tool_attempt_entry(label, entry, parts)
            attempt_parts.append(attempt_label)
        if attempt_parts:
            parts.insert(0, "attempts=" + ", ".join(attempt_parts))
    
    details = tool_summary.get("details")
    if details:
        parts.append(_stringify_healthcheck_detail(details))
    
    return "; ".join(parts) if parts else "-"


def _create_healthcheck_table() -> Table:
    """Create the healthcheck summary table with columns."""
    table = Table(title="Healthcheck Summary", box=box.SIMPLE_HEAVY)
    table.add_column("Check", style=_RichStyles.ACCENT)
    table.add_column("Context", style=_RichStyles.SECONDARY)
    table.add_column("Tool", style=_RichStyles.SUCCESS)
    table.add_column("Status", style=_RichStyles.EMPHASIS)
    table.add_column("Details", style=_RichStyles.DETAIL)
    return table


def _add_healthcheck_offline_row(table: Table, report: dict[str, Any]) -> None:
    """Add the offline check row to the healthcheck table."""
    offline_entry = report.get("offline_check", {})
    offline_status = _healthcheck_status_label(offline_entry.get("status"))
    offline_detail = _stringify_healthcheck_detail(offline_entry.get("details"))
    table.add_row("Offline checks", "-", "-", offline_status, offline_detail)


def _determine_context_status(context_data: Mapping[str, Any]) -> str:
    """Determine the status label for a context."""
    context_success = context_data.get("success")
    offline_mode = context_data.get("offline_mode")
    if offline_mode and context_success:
        return "warning"
    elif context_success:
        return "pass"
    else:
        return "fail"


def _add_healthcheck_context_rows(
    table: Table,
    context_name: str,
    context_data: Mapping[str, Any],
) -> None:
    """Add context, online, and tool rows for a single context."""
    context_status = _determine_context_status(context_data)
    context_detail = _format_healthcheck_context_detail(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    table.add_row("Context", context_name, "-", context_status_label, context_detail)

    online_summary = context_data.get("online", {})
    online_status_label = _healthcheck_status_label(online_summary.get("status"))
    online_detail = _format_healthcheck_online_detail(online_summary)
    table.add_row("Online", context_name, "-", online_status_label, online_detail or "-")

    tools = context_data.get("tools", {})
    for tool_name, tool_summary in sorted(tools.items()):
        tool_status_label = _healthcheck_status_label(tool_summary.get("status"))
        detail_text = _format_healthcheck_tool_detail(tool_summary)
        table.add_row("Tool", context_name, tool_name, tool_status_label, detail_text)


def _collect_healthcheck_critical_failures(
    context_name: str,
    context_data: Mapping[str, Any],
) -> list[str]:
    """Collect critical failure messages for a context."""
    failures: list[str] = []
    context_status = _determine_context_status(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    
    if context_status_label == "FAIL":
        failures.append(f"{context_name}: context failure")
    
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        failures.append(
            f"{context_name}: unrecoverable={','.join(sorted(unrecoverable))}"
        )
    
    return failures


def _render_healthcheck_summary(report: dict[str, Any]) -> None:
    """Render a comprehensive healthcheck summary table and JSON report."""
    table = _create_healthcheck_table()
    _add_healthcheck_offline_row(table, report)

    critical_failures: list[str] = []
    for context_name, context_data in sorted(report.get("contexts", {}).items()):
        _add_healthcheck_context_rows(table, context_name, context_data)
        critical_failures.extend(
            _collect_healthcheck_critical_failures(context_name, context_data)
        )

    if critical_failures:
        table.add_row(
            "Critical failures",
            "-",
            "-",
            "FAIL",
            "; ".join(critical_failures),
        )

    stdout_console.print()
    stdout_console.print(table)
    stdout_console.print()
    stdout_console.print("Machine-readable summary:")
    stdout_console.print(json.dumps(report, indent=2, sort_keys=True))


def _format_exception_message(exc: BaseException) -> str:
    return str(exc)


def _validate_company_entry(entry: Any, logger: BoundLogger) -> bool:
    """Validate a single company entry in search results."""
    if not isinstance(entry, dict):
        logger.critical("healthcheck.company_search.invalid_company", reason="entry not dict")
        return False
    if not entry.get("guid") or not entry.get("name"):
        logger.critical(
            "healthcheck.company_search.invalid_company",
            reason="missing guid/name",
            company=entry,
        )
        return False
    return True


def _check_domain_match(companies: list, expected_domain: str, logger: BoundLogger) -> bool:
    """Check if expected domain is present in company list."""
    for entry in companies:
        domain_value = str(entry.get("domain") or "")
        if domain_value.lower() == expected_domain.lower():
            return True
    logger.critical("healthcheck.company_search.domain_missing", expected=expected_domain)
    return False


def _validate_company_search_payload(
    payload: Any,
    *,
    logger: BoundLogger,
    expected_domain: str | None = None,
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.company_search.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.company_search.api_error", error=str(payload["error"]))
        return False

    companies = payload.get("companies")
    if not isinstance(companies, list) or not companies:
        logger.critical("healthcheck.company_search.empty", reason="no companies returned")
        return False

    for entry in companies:
        if not _validate_company_entry(entry, logger):
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical("healthcheck.company_search.invalid_count", count=count_value)
        return False

    if expected_domain and not _check_domain_match(companies, expected_domain, logger):
        return False

    return True


def _validate_rating_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.rating.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.rating.api_error", error=str(payload["error"]))
        return False

    required_fields = ("name", "domain", "current_rating", "top_findings", "legend")
    for field in required_fields:
        if payload.get(field) in (None, {}):
            logger.critical("healthcheck.rating.missing_field", field=field)
            return False

    current_rating = payload.get("current_rating")
    if not isinstance(current_rating, dict) or current_rating.get("value") is None:
        logger.critical("healthcheck.rating.invalid_current_rating", payload=current_rating)
        return False

    findings = payload.get("top_findings")
    if not isinstance(findings, dict):
        logger.critical("healthcheck.rating.invalid_findings", payload=findings)
        return False

    finding_count = findings.get("count")
    finding_entries = findings.get("findings")
    if not isinstance(finding_count, int) or finding_count <= 0:
        logger.critical("healthcheck.rating.no_findings", count=finding_count)
        return False
    if not isinstance(finding_entries, list) or not finding_entries:
        logger.critical("healthcheck.rating.empty_findings", payload=findings)
        return False

    legend = payload.get("legend")
    if not isinstance(legend, dict) or not legend.get("rating"):
        logger.critical("healthcheck.rating.missing_legend", payload=legend)
        return False

    return True


def _validate_company_search_interactive_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical(
            "healthcheck.company_search_interactive.invalid_response", reason=MSG_NOT_A_DICT
        )
        return False

    if payload.get("error"):
        logger.critical(
            "healthcheck.company_search_interactive.api_error",
            error=str(payload["error"]),
        )
        return False

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        logger.critical(
            "healthcheck.company_search_interactive.empty_results",
            reason="no interactive results",
        )
        return False

    for entry in results:
        if not isinstance(entry, dict):
            logger.critical(
                "healthcheck.company_search_interactive.invalid_entry",
                reason="entry not dict",
            )
            return False
        required_keys = ("guid", "name", "primary_domain", "subscription")
        if any(not entry.get(key) for key in required_keys):
            logger.critical(
                "healthcheck.company_search_interactive.missing_fields",
                entry=entry,
            )
            return False
        subscription = entry.get("subscription")
        if not isinstance(subscription, dict) or "active" not in subscription:
            logger.critical(
                "healthcheck.company_search_interactive.invalid_subscription",
                subscription=subscription,
            )
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical(
            "healthcheck.company_search_interactive.invalid_count",
            count=count_value,
        )
        return False

    guidance = payload.get("guidance")
    if not isinstance(guidance, dict):
        logger.critical("healthcheck.company_search_interactive.missing_guidance")
        return False

    return True


def _validate_manage_subscriptions_payload(
    payload: Any, *, logger: BoundLogger, expected_guid: str
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.manage_subscriptions.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.manage_subscriptions.api_error", error=str(payload["error"]))
        return False

    status = payload.get("status")
    if status not in {"dry_run", "applied"}:
        logger.critical("healthcheck.manage_subscriptions.unexpected_status", status=status)
        return False

    guids = payload.get("guids")
    if not isinstance(guids, list) or expected_guid not in guids:
        logger.critical(
            "healthcheck.manage_subscriptions.guid_missing",
            guids=guids,
            expected=expected_guid,
        )
        return False

    if status == "dry_run":
        dry_payload = payload.get("payload")
        if not isinstance(dry_payload, dict) or "add" not in dry_payload:
            logger.critical(
                "healthcheck.manage_subscriptions.invalid_payload",
                payload=dry_payload,
            )
            return False

    return True


def _healthcheck_status_label(value: str | None) -> str:
    """Convert status value to uppercase label."""
    mapping = {"pass": "PASS", "fail": "FAIL", "warning": "WARNING"}
    if not value:
        return "WARNING"
    return mapping.get(value.lower(), value.upper())


def _stringify_healthcheck_detail(value: Any) -> str:
    """Convert any value to a string representation for healthcheck display."""
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        items = [f"{key}={value[key]}" for key in sorted(value)]
        return ", ".join(items) if items else "-"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = [_stringify_healthcheck_detail(item) for item in value]
        return ", ".join(item for item in items if item and item != "-") or "-"
    return str(value)


def _format_healthcheck_context_detail(context_data: Mapping[str, Any]) -> str:
    """Format context diagnostic details into a summary string."""
    parts: list[str] = []
    if context_data.get("fallback_attempted"):
        resolved = context_data.get("fallback_success")
        parts.append("fallback=" + ("resolved" if resolved else "failed"))
    recoverable = context_data.get("recoverable_categories") or []
    if recoverable:
        parts.append("recoverable=" + ",".join(sorted(recoverable)))
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        parts.append("unrecoverable=" + ",".join(sorted(unrecoverable)))
    notes = context_data.get("notes") or []
    if notes:
        parts.append("notes=" + ",".join(notes))
    return "; ".join(parts) if parts else "-"


def _format_healthcheck_online_detail(online_data: Mapping[str, Any]) -> str:
    """Format online diagnostic details into a summary string."""
    attempts = online_data.get("attempts") if isinstance(online_data, Mapping) else None
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = [
            f"{label}:{_healthcheck_status_label(status)}"
            for label, status in sorted(attempts.items())
        ]
        return ", ".join(attempt_parts)
    details = online_data.get("details") if isinstance(online_data, Mapping) else None
    return _stringify_healthcheck_detail(details)


def _process_tool_attempt_entry(
    label: str,
    entry: Mapping[str, Any],
    parts: list[str],
) -> str:
    """Process a single tool attempt entry and return its status label."""
    attempt_status = _healthcheck_status_label(entry.get("status"))
    
    modes = entry.get("modes")
    if isinstance(modes, Mapping) and modes:
        mode_parts = [
            f"{mode}:{_healthcheck_status_label(mode_entry.get('status'))}"
            for mode, mode_entry in sorted(modes.items())
        ]
        if mode_parts:
            parts.append(f"{label} modes=" + ", ".join(mode_parts))
    
    detail = entry.get("details")
    if detail:
        parts.append(f"{label} detail=" + _stringify_healthcheck_detail(detail))
    
    return f"{label}:{attempt_status}"


def _format_healthcheck_tool_detail(tool_summary: Mapping[str, Any]) -> str:
    """Format tool diagnostic details into a summary string."""
    parts: list[str] = []
    attempts = tool_summary.get("attempts")
    if isinstance(attempts, Mapping) and attempts:
        attempt_parts = []
        for label, entry in sorted(attempts.items()):
            attempt_label = _process_tool_attempt_entry(label, entry, parts)
            attempt_parts.append(attempt_label)
        if attempt_parts:
            parts.insert(0, "attempts=" + ", ".join(attempt_parts))
    
    details = tool_summary.get("details")
    if details:
        parts.append(_stringify_healthcheck_detail(details))
    
    return "; ".join(parts) if parts else "-"


def _create_healthcheck_table() -> Table:
    """Create the healthcheck summary table with columns."""
    table = Table(title="Healthcheck Summary", box=box.SIMPLE_HEAVY)
    table.add_column("Check", style=_RichStyles.ACCENT)
    table.add_column("Context", style=_RichStyles.SECONDARY)
    table.add_column("Tool", style=_RichStyles.SUCCESS)
    table.add_column("Status", style=_RichStyles.EMPHASIS)
    table.add_column("Details", style=_RichStyles.DETAIL)
    return table


def _add_healthcheck_offline_row(table: Table, report: dict[str, Any]) -> None:
    """Add the offline check row to the healthcheck table."""
    offline_entry = report.get("offline_check", {})
    offline_status = _healthcheck_status_label(offline_entry.get("status"))
    offline_detail = _stringify_healthcheck_detail(offline_entry.get("details"))
    table.add_row("Offline checks", "-", "-", offline_status, offline_detail)


def _determine_context_status(context_data: Mapping[str, Any]) -> str:
    """Determine the status label for a context."""
    context_success = context_data.get("success")
    offline_mode = context_data.get("offline_mode")
    if offline_mode and context_success:
        return "warning"
    elif context_success:
        return "pass"
    else:
        return "fail"


def _add_healthcheck_context_rows(
    table: Table,
    context_name: str,
    context_data: Mapping[str, Any],
) -> None:
    """Add context, online, and tool rows for a single context."""
    context_status = _determine_context_status(context_data)
    context_detail = _format_healthcheck_context_detail(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    table.add_row("Context", context_name, "-", context_status_label, context_detail)

    online_summary = context_data.get("online", {})
    online_status_label = _healthcheck_status_label(online_summary.get("status"))
    online_detail = _format_healthcheck_online_detail(online_summary)
    table.add_row("Online", context_name, "-", online_status_label, online_detail or "-")

    tools = context_data.get("tools", {})
    for tool_name, tool_summary in sorted(tools.items()):
        tool_status_label = _healthcheck_status_label(tool_summary.get("status"))
        detail_text = _format_healthcheck_tool_detail(tool_summary)
        table.add_row("Tool", context_name, tool_name, tool_status_label, detail_text)


def _collect_healthcheck_critical_failures(
    context_name: str,
    context_data: Mapping[str, Any],
) -> list[str]:
    """Collect critical failure messages for a context."""
    failures: list[str] = []
    context_status = _determine_context_status(context_data)
    context_status_label = _healthcheck_status_label(context_status)
    
    if context_status_label == "FAIL":
        failures.append(f"{context_name}: context failure")
    
    unrecoverable = context_data.get("unrecoverable_categories") or []
    if unrecoverable:
        failures.append(
            f"{context_name}: unrecoverable={','.join(sorted(unrecoverable))}"
        )
    
    return failures


def _render_healthcheck_summary(report: dict[str, Any]) -> None:
    """Render a comprehensive healthcheck summary table and JSON report."""
    table = _create_healthcheck_table()
    _add_healthcheck_offline_row(table, report)

    critical_failures: list[str] = []
    for context_name, context_data in sorted(report.get("contexts", {}).items()):
        _add_healthcheck_context_rows(table, context_name, context_data)
        critical_failures.extend(
            _collect_healthcheck_critical_failures(context_name, context_data)
        )

    if critical_failures:
        table.add_row(
            "Critical failures",
            "-",
            "-",
            "FAIL",
            "; ".join(critical_failures),
        )

    stdout_console.print()
    stdout_console.print(table)
    stdout_console.print()
    stdout_console.print("Machine-readable summary:")
    stdout_console.print(json.dumps(report, indent=2, sort_keys=True))


def _format_exception_message(exc: BaseException) -> str:
    return str(exc)


def _validate_company_entry(entry: Any, logger: BoundLogger) -> bool:
    """Validate a single company entry in search results."""
    if not isinstance(entry, dict):
        logger.critical("healthcheck.company_search.invalid_company", reason="entry not dict")
        return False
    if not entry.get("guid") or not entry.get("name"):
        logger.critical(
            "healthcheck.company_search.invalid_company",
            reason="missing guid/name",
            company=entry,
        )
        return False
    return True


def _check_domain_match(companies: list, expected_domain: str, logger: BoundLogger) -> bool:
    """Check if expected domain is present in company list."""
    for entry in companies:
        domain_value = str(entry.get("domain") or "")
        if domain_value.lower() == expected_domain.lower():
            return True
    logger.critical("healthcheck.company_search.domain_missing", expected=expected_domain)
    return False


def _validate_company_search_payload(
    payload: Any,
    *,
    logger: BoundLogger,
    expected_domain: str | None = None,
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.company_search.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.company_search.api_error", error=str(payload["error"]))
        return False

    companies = payload.get("companies")
    if not isinstance(companies, list) or not companies:
        logger.critical("healthcheck.company_search.empty", reason="no companies returned")
        return False

    for entry in companies:
        if not _validate_company_entry(entry, logger):
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical("healthcheck.company_search.invalid_count", count=count_value)
        return False

    if expected_domain and not _check_domain_match(companies, expected_domain, logger):
        return False

    return True


def _validate_rating_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.rating.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.rating.api_error", error=str(payload["error"]))
        return False

    required_fields = ("name", "domain", "current_rating", "top_findings", "legend")
    for field in required_fields:
        if payload.get(field) in (None, {}):
            logger.critical("healthcheck.rating.missing_field", field=field)
            return False

    current_rating = payload.get("current_rating")
    if not isinstance(current_rating, dict) or current_rating.get("value") is None:
        logger.critical("healthcheck.rating.invalid_current_rating", payload=current_rating)
        return False

    findings = payload.get("top_findings")
    if not isinstance(findings, dict):
        logger.critical("healthcheck.rating.invalid_findings", payload=findings)
        return False

    finding_count = findings.get("count")
    finding_entries = findings.get("findings")
    if not isinstance(finding_count, int) or finding_count <= 0:
        logger.critical("healthcheck.rating.no_findings", count=finding_count)
        return False
    if not isinstance(finding_entries, list) or not finding_entries:
        logger.critical("healthcheck.rating.empty_findings", payload=findings)
        return False

    legend = payload.get("legend")
    if not isinstance(legend, dict) or not legend.get("rating"):
        logger.critical("healthcheck.rating.missing_legend", payload=legend)
        return False

    return True


def _validate_company_search_interactive_payload(payload: Any, *, logger: BoundLogger) -> bool:
    if not isinstance(payload, dict):
        logger.critical(
            "healthcheck.company_search_interactive.invalid_response", reason=MSG_NOT_A_DICT
        )
        return False

    if payload.get("error"):
        logger.critical(
            "healthcheck.company_search_interactive.api_error",
            error=str(payload["error"]),
        )
        return False

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        logger.critical(
            "healthcheck.company_search_interactive.empty_results",
            reason="no interactive results",
        )
        return False

    for entry in results:
        if not isinstance(entry, dict):
            logger.critical(
                "healthcheck.company_search_interactive.invalid_entry",
                reason="entry not dict",
            )
            return False
        required_keys = ("guid", "name", "primary_domain", "subscription")
        if any(not entry.get(key) for key in required_keys):
            logger.critical(
                "healthcheck.company_search_interactive.missing_fields",
                entry=entry,
            )
            return False
        subscription = entry.get("subscription")
        if not isinstance(subscription, dict) or "active" not in subscription:
            logger.critical(
                "healthcheck.company_search_interactive.invalid_subscription",
                subscription=subscription,
            )
            return False

    count_value = payload.get("count")
    if not isinstance(count_value, int) or count_value <= 0:
        logger.critical(
            "healthcheck.company_search_interactive.invalid_count",
            count=count_value,
        )
        return False

    guidance = payload.get("guidance")
    if not isinstance(guidance, dict):
        logger.critical("healthcheck.company_search_interactive.missing_guidance")
        return False

    return True


def _validate_manage_subscriptions_payload(
    payload: Any, *, logger: BoundLogger, expected_guid: str
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.manage_subscriptions.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.manage_subscriptions.api_error", error=str(payload["error"]))
        return False

    status = payload.get("status")
    if status not in {"dry_run", "applied"}:
        logger.critical("healthcheck.manage_subscriptions.unexpected_status", status=status)
        return False

    guids = payload.get("guids")
    if not isinstance(guids, list) or expected_guid not in guids:
        logger.critical(
            "healthcheck.manage_subscriptions.guid_missing",
            guids=guids,
            expected=expected_guid,
        )
        return False

    if status == "dry_run":
        dry_payload = payload.get("payload")
        if not isinstance(dry_payload, dict) or "add" not in dry_payload:
            logger.critical(
                "healthcheck.manage_subscriptions.invalid_payload",
                payload=dry_payload,
            )
            return False

    return True


def _validate_request_company_payload(
    payload: Any, *, logger: BoundLogger, expected_domain: str
) -> bool:
    if not isinstance(payload, dict):
        logger.critical("healthcheck.request_company.invalid_response", reason=MSG_NOT_A_DICT)
        return False

    if payload.get("error"):
        logger.critical("healthcheck.request_company.api_error", error=str(payload["error"]))
        return False

    status = payload.get("status")
    if status not in {"dry_run", "already_requested"}:
        logger.critical("healthcheck.request_company.unexpected_status", status=status)
        return False

    domain_value = payload.get("domain")
    if not isinstance(domain_value, str) or domain_value.lower() != expected_domain.lower():
        logger.critical(
            "healthcheck.request_company.domain_mismatch",
            domain=domain_value,
            expected=expected_domain,
        )
        return False

    if status == "dry_run":
        dry_payload = payload.get("payload")
        if not isinstance(dry_payload, dict) or "file" not in dry_payload:
            logger.critical("healthcheck.request_company.invalid_payload", payload=dry_payload)
            return False
    else:
        requests = payload.get("requests")
        if not isinstance(requests, list):
            logger.critical(
                "healthcheck.request_company.invalid_requests",
                requests=requests,
            )
            return False

    return True





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
