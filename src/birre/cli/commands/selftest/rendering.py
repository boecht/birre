"""Rendering functions for selftest command output."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table


class _RichStyles:
    """Rich console style constants."""

    ACCENT = "bold cyan"
    SECONDARY = "magenta"
    SUCCESS = "green"
    EMPHASIS = "bold"
    DETAIL = "white"


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
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
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
    table.add_row(
        "Online", context_name, "-", online_status_label, online_detail or "-"
    )

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


def render_healthcheck_summary(report: dict[str, Any], stdout_console: Console) -> None:
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
    stdout_console.print("Machine-readable summary:")
    stdout_console.print(
        json.dumps(report, indent=2, separators=(",", ": "), sort_keys=True)
    )
    stdout_console.print()
    stdout_console.print(table)
