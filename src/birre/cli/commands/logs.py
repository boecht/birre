"""Log maintenance commands for BiRRe CLI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from birre.cli import options as cli_options
from birre.cli.invocation import (
    LoggingCliInputs,
    build_invocation,
    resolve_runtime_and_logging,
)
from birre.cli.models import CliInvocation, LogViewLine
from birre.cli.runtime import CONTEXT_CHOICES
from birre.cli.validation import validate_path_exists
from birre.config.constants import DEFAULT_CONFIG_FILENAME
from birre.domain.company_rating.constants import DEFAULT_LOG_TAIL_LINES


def _rotate_logs(base_path: Path, backup_count: int) -> None:
    """Rotate log files with numbered backups."""
    if backup_count <= 0:
        base_path.write_text("", encoding="utf-8")
        return

    for index in range(backup_count, 0, -1):
        source = base_path.with_name(f"{base_path.name}.{index}")
        target = base_path.with_name(f"{base_path.name}.{index + 1}")
        if validate_path_exists(source):
            source.replace(target)

    if validate_path_exists(base_path):
        base_path.replace(base_path.with_name(f"{base_path.name}.1"))
    base_path.touch()


def _resolve_logging_settings_from_cli(
    *,
    config_path: Path | None,
    log_level: str | None,
    log_format: str | None,
    log_file: str | None,
    log_max_bytes: int | None,
    log_backup_count: int | None,
) -> tuple[CliInvocation, Any]:
    """Resolve logging settings from CLI parameters."""
    invocation = build_invocation(
        config_path=str(config_path) if config_path is not None else None,
        context_choices=CONTEXT_CHOICES,
        logging=LoggingCliInputs(
            level=log_level,
            format=log_format,
            file_path=log_file,
            max_bytes=log_max_bytes,
            backup_count=log_backup_count,
        ),
    )
    _, logging_settings, _ = resolve_runtime_and_logging(invocation)
    return invocation, logging_settings


def _parse_iso_timestamp_to_epoch(value: str) -> float | None:
    """Parse ISO 8601 timestamp string to Unix epoch."""
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return parsed.timestamp()


def _parse_relative_duration(value: str) -> timedelta | None:
    """Parse relative duration string like '30m', '1h', '2d' to timedelta."""
    import re

    if value is None:
        return None
    pattern = re.compile(r"^\s*(\d+)([smhd])\s*$", re.IGNORECASE)
    match = pattern.match(value)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    multiplier = {
        "s": timedelta(seconds=1),
        "m": timedelta(minutes=1),
        "h": timedelta(hours=1),
        "d": timedelta(days=1),
    }.get(unit)
    if multiplier is None:
        return None
    return multiplier * amount


def _parse_json_log_line(stripped: str) -> LogViewLine:
    """Parse a JSON-formatted log line."""
    import json

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return LogViewLine(raw=stripped, level=None, timestamp=None, json_data=None)

    timestamp = None
    for key in ("timestamp", "time", "@timestamp", "ts"):
        value = data.get(key)
        if isinstance(value, str):
            timestamp = _parse_iso_timestamp_to_epoch(value)
            if timestamp is not None:
                break

    level_value = data.get("level") or data.get("levelname") or data.get("severity")
    if isinstance(level_value, str):
        level = cli_options.LOG_LEVEL_MAP.get(level_value.strip().upper())
    elif isinstance(level_value, int):
        level = level_value
    else:
        level = None

    return LogViewLine(raw=stripped, level=level, timestamp=timestamp, json_data=data)


def _parse_text_log_line(stripped: str) -> LogViewLine:
    """Parse a text-formatted log line."""
    timestamp = None
    level = None
    tokens = stripped.split()

    if tokens:
        timestamp = _parse_iso_timestamp_to_epoch(tokens[0].strip("[]"))
        for token in tokens[:3]:
            candidate = cli_options.LOG_LEVEL_MAP.get(token.strip("[]:,").upper())
            if candidate is not None:
                level = candidate
                break

    return LogViewLine(raw=stripped, level=level, timestamp=timestamp, json_data=None)


def _parse_log_line(line: str, format_hint: str) -> LogViewLine:
    """Parse a log line based on format hint."""
    stripped = line.rstrip("\n")
    if format_hint == "json":
        return _parse_json_log_line(stripped)
    return _parse_text_log_line(stripped)


def _validate_logs_show_params(
    tail: int,
    since: str | None,
    last: str | None,
    format_override: str | None,
) -> str | None:
    """Validate logs_show parameters. Returns normalized format or None."""
    if tail < 0:
        raise typer.BadParameter(
            "Tail must be greater than or equal to zero.", param_hint="--tail"
        )
    if since and last:
        raise typer.BadParameter(
            "Only one of --since or --last can be provided.", param_hint="--since"
        )

    if format_override is not None:
        normalized = format_override.strip().lower()
        if normalized not in cli_options.LOG_FORMAT_CHOICES:
            raise typer.BadParameter(
                "Format must be either 'text' or 'json'.", param_hint="--format"
            )
        return normalized
    return None


def _resolve_start_timestamp(since: str | None, last: str | None) -> float | None:
    """Calculate start timestamp from --since or --last options."""
    if since:
        timestamp = _parse_iso_timestamp_to_epoch(since)
        if timestamp is None:
            raise typer.BadParameter(
                "Invalid ISO 8601 timestamp.", param_hint="--since"
            )
        return timestamp

    if last:
        duration = _parse_relative_duration(last)
        if duration is None:
            raise typer.BadParameter(
                "Invalid relative duration; use values like 30m, 1h, or 2d.",
                param_hint="--last",
            )
        return (datetime.now(UTC) - duration).timestamp()

    return None


def _should_include_log_entry(
    parsed: LogViewLine,
    level_threshold: int | None,
    normalized_level: str | None,
    start_timestamp: float | None,
) -> bool:
    """Check if log entry passes level and timestamp filters."""
    if level_threshold is not None:
        if parsed.level is not None:
            if parsed.level < level_threshold:
                return False
        elif normalized_level is not None:
            if normalized_level not in parsed.raw.upper():
                return False

    if start_timestamp is not None:
        if parsed.timestamp is None or parsed.timestamp < start_timestamp:
            return False

    return True


def _display_log_entries(
    matched: list[LogViewLine],
    resolved_format: str,
    stdout_console: Console,
) -> None:
    """Display filtered log entries to stdout."""
    if not matched:
        stdout_console.print(
            "[yellow]No log entries matched the supplied filters[/yellow]"
        )
        return

    for entry in matched:
        if resolved_format == "json" and entry.json_data is not None:
            stdout_console.print_json(data=entry.json_data)
        else:
            stdout_console.print(entry.raw, markup=False, highlight=False)


def _cmd_logs_clear(
    config: Path,
    log_file: str | None,
    stdout_console: Console,
) -> None:
    """Implementation of logs clear command."""
    _, logging_settings = _resolve_logging_settings_from_cli(
        config_path=config,
        log_level=None,
        log_format=None,
        log_file=log_file,
        log_max_bytes=None,
        log_backup_count=None,
    )
    file_path = getattr(logging_settings, "file_path", None)
    if not file_path:
        stdout_console.print(
            "[yellow]File logging is disabled; nothing to clear[/yellow]"
        )
        return

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text("", encoding="utf-8")
    except OSError as exc:
        raise typer.BadParameter(f"Failed to clear log file: {exc}") from exc
    stdout_console.print(f"[green]Log file cleared at[/green] {path}")


def _cmd_logs_rotate(
    config: Path,
    log_file: str | None,
    log_backup_count: int | None,
    stdout_console: Console,
) -> None:
    """Implementation of logs rotate command."""
    _, logging_settings = _resolve_logging_settings_from_cli(
        config_path=config,
        log_level=None,
        log_format=None,
        log_file=log_file,
        log_max_bytes=None,
        log_backup_count=log_backup_count,
    )
    file_path = getattr(logging_settings, "file_path", None)
    if not file_path:
        stdout_console.print(
            "[yellow]File logging is disabled; nothing to rotate[/yellow]"
        )
        return

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_count = (
        log_backup_count
        if log_backup_count is not None
        else getattr(logging_settings, "backup_count", 0) or 0
    )
    _rotate_logs(path, backup_count)
    stdout_console.print(f"[green]Log files rotated at[/green] {path}")


def _cmd_logs_path(
    config: Path,
    log_file: str | None,
    stdout_console: Console,
) -> None:
    """Implementation of logs path command."""
    _, logging_settings = _resolve_logging_settings_from_cli(
        config_path=config,
        log_level=None,
        log_format=None,
        log_file=log_file,
        log_max_bytes=None,
        log_backup_count=None,
    )
    file_path = getattr(logging_settings, "file_path", None)
    if not file_path:
        stdout_console.print("[yellow]File logging is disabled[/yellow]")
        return
    resolved = Path(file_path)
    absolute = resolved.expanduser()
    try:
        absolute = absolute.resolve(strict=False)
    except OSError:
        absolute = absolute.absolute()

    stdout_console.print(f"[green]Log file (relative)[/green]: {resolved}")
    stdout_console.print(f"[green]Log file (absolute)[/green]: {absolute}")


def _cmd_logs_show(
    config: Path,
    log_file: str | None,
    level: str | None,
    tail: int,
    since: str | None,
    last: str | None,
    format_override: str | None,
    stdout_console: Console,
) -> None:
    """Implementation of logs show command."""
    normalized_format = _validate_logs_show_params(tail, since, last, format_override)
    normalized_level = (
        cli_options.normalize_log_level(level) if level is not None else None
    )
    level_threshold = (
        cli_options.LOG_LEVEL_MAP.get(normalized_level) if normalized_level else None
    )

    _, logging_settings = _resolve_logging_settings_from_cli(
        config_path=config,
        log_level=None,
        log_format=None,
        log_file=log_file,
        log_max_bytes=None,
        log_backup_count=None,
    )
    file_path = getattr(logging_settings, "file_path", None)
    resolved_format = (
        normalized_format or getattr(logging_settings, "format", None) or "text"
    )

    if not file_path:
        stdout_console.print(
            "[yellow]File logging is disabled; nothing to show[/yellow]"
        )
        return

    path = Path(file_path)
    if not validate_path_exists(path):
        stdout_console.print(f"[yellow]Log file not found at[/yellow] {path}")
        return

    start_timestamp = _resolve_start_timestamp(since, last)

    matched: list[LogViewLine] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parsed = _parse_log_line(line, resolved_format)
            if _should_include_log_entry(
                parsed,
                level_threshold,
                normalized_level,
                start_timestamp,
            ):
                matched.append(parsed)

    if tail and tail > 0:
        matched = matched[-tail:]

    _display_log_entries(matched, resolved_format, stdout_console)


def register(
    app: typer.Typer,
    *,
    stdout_console: Console,
) -> None:
    """Register logs commands with the app."""
    # Logs subcommands group
    logs_app = typer.Typer(
        help="Inspect and maintain BiRRe log files.",
        invoke_without_command=True,
        no_args_is_help=True,
    )
    app.add_typer(logs_app, name="logs")

    @logs_app.callback(invoke_without_command=True)
    def logs_group_callback(ctx: typer.Context) -> None:
        """Display help when logs group is invoked without a subcommand."""
        if ctx.invoked_subcommand is None:
            typer.echo(ctx.get_help())
            raise typer.Exit()

    @logs_app.command(
        "clear",
        help="Truncate the active BiRRe log file while leaving rotated archives untouched.",
    )
    def logs_clear(
        config: cli_options.ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
        log_file: cli_options.LogFileOption = None,
    ) -> None:
        """Truncate the resolved log file."""
        _cmd_logs_clear(config, log_file, stdout_console)

    @logs_app.command(
        "rotate",
        help="Perform a manual log rotation using the configured backup count.",
    )
    def logs_rotate(
        config: cli_options.ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
        log_file: cli_options.LogFileOption = None,
        log_backup_count: cli_options.LogBackupCountOption = None,
    ) -> None:
        """Rotate the active log file into numbered archives."""
        _cmd_logs_rotate(config, log_file, log_backup_count, stdout_console)

    @logs_app.command(
        "path",
        help="Show the resolved BiRRe log file path after applying configuration overrides.",
    )
    def logs_path(
        config: cli_options.ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
        log_file: cli_options.LogFileOption = None,
    ) -> None:
        """Print the effective log file path."""
        _cmd_logs_path(config, log_file, stdout_console)

    @logs_app.command(
        "show",
        help="Display recent log entries with optional level and time filtering.",
    )
    def logs_show(
        config: cli_options.ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
        log_file: cli_options.LogFileOption = None,
        level: str | None = typer.Option(
            None,
            "--level",
            help="Minimum log level to include (e.g. INFO, WARNING).",
            rich_help_panel="Filtering",
        ),
        tail: int = typer.Option(
            DEFAULT_LOG_TAIL_LINES,
            "--tail",
            help="Number of lines from the end of the log to display (0 to show all).",
            rich_help_panel="Filtering",
        ),
        since: str | None = typer.Option(
            None,
            "--since",
            help="Only include entries at or after the given ISO 8601 timestamp.",
            rich_help_panel="Filtering",
        ),
        last: str | None = typer.Option(
            None,
            "--last",
            help="Only include entries from the relative window (e.g. 1h, 30m).",
            rich_help_panel="Filtering",
        ),
        format_override: str | None = typer.Option(
            None,
            "--format",
            case_sensitive=False,
            help="Treat log entries as 'json' or 'text'. Defaults to the configured format.",
            rich_help_panel="Presentation",
        ),
    ) -> None:
        """Render log entries to stdout."""
        _cmd_logs_show(
            config,
            log_file,
            level,
            tail,
            since,
            last,
            format_override,
            stdout_console,
        )
