"""Config management commands for BiRRe CLI."""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import click
import typer
from click.core import ParameterSource
from rich import box
from rich.console import Console
from rich.table import Table

from birre.cli import options as cli_options
from birre.cli.formatting import (
    RichStyles,
    create_config_table,
    flatten_to_dotted,
    format_config_value,
    mask_sensitive_value,
)
from birre.cli.helpers import CONTEXT_CHOICES, build_invocation, resolve_runtime_and_logging
from birre.cli.models import CliInvocation
from birre.cli.validation import parse_toml_file, require_file_exists
from birre.config.constants import (
    DEFAULT_CONFIG_FILENAME,
    LOCAL_CONFIG_FILENAME,
)
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
    load_settings,
    resolve_config_file_candidates,
)

# Constants
SOURCE_USER_INPUT: Final = "User Input"


# Helper functions for config commands


def _prompt_bool(prompt: str, default: bool) -> bool:
    """Prompt for a boolean value."""
    return typer.confirm(prompt, default=default)


def _prompt_str(
    prompt: str, default: str | None, secret: bool = False
) -> str | None:
    """Prompt for a string value."""
    value = typer.prompt(
        prompt, default=default or "", hide_input=secret
    ).strip()
    return value or None


def _validate_and_apply_normalizer(
    response: str | None,
    *,
    required: bool,
    normalizer: Callable[[str, str | None], str | None] | None,
) -> str | None:
    """Apply normalizer and validate the result."""
    def _apply(value: str | None) -> str | None:
        cleaned = cli_options.clean_string(value)
        if cleaned is None:
            return None
        if normalizer is None:
            return cleaned
        return normalizer(cleaned, None)

    try:
        normalized = _apply(response)
    except typer.BadParameter:
        return None

    if normalized is None and required:
        return None

    return normalized


def _collect_or_prompt_string(
    provided: str | None,
    *,
    prompt: str,
    default: str | None,
    secret: bool = False,
    required: bool = False,
    normalizer: Callable[[str, str | None], str | None] | None = None,
) -> str | None:
    """Return a CLI-provided string or interactively prompt for one."""
    def _apply(value: str | None) -> str | None:
        cleaned = cli_options.clean_string(value)
        if cleaned is None:
            return None
        if normalizer is None:
            return cleaned
        return normalizer(cleaned, None)

    if provided is not None:
        return _apply(provided)

    while True:
        response = _prompt_str(prompt, default, secret=secret)
        if response is None:
            if required:
                typer.echo("A value is required")
                continue
            return None

        normalized = _validate_and_apply_normalizer(
            response, required=required, normalizer=normalizer
        )
        if normalized is not None or not required:
            return normalized


def _format_config_value(value: Any) -> str:
    """Format a value for TOML configuration file."""
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        formatted = ", ".join(_format_config_value(item) for item in value)
        return f"[{formatted}]"
    return f'"{value}"'


def _format_config_section(
    section: str, section_values: dict[str, Any]
) -> list[str]:
    """Format a single config section."""
    if not isinstance(section_values, dict) or not section_values:
        return []
    
    lines = ["", f"[{section}]"]
    for key, entry in sorted(section_values.items()):
        if entry is None:
            continue
        if isinstance(entry, str) and not entry.strip():
            continue
        lines.append(f"{key} = {_format_config_value(entry)}")
    return lines


def _generate_local_config_content(
    values: dict[str, Any], *, include_header: bool = True
) -> str:
    """Generate TOML content from config values."""
    lines: list[str] = []
    if include_header:
        lines.append("## Generated local configuration")

    for section, section_values in sorted(values.items()):
        lines.extend(_format_config_section(section, section_values))
    
    lines.append("")
    return "\n".join(lines)


def _determine_value_source(value, default_value, normalizer):
    """Determine the source of a prompted value (Default vs User Input)."""
    if default_value and value == default_value:
        return "Default"
    
    if normalizer:
        normalized_default = (
            normalizer(default_value, None) if default_value else None
        )
        normalized_value = normalizer(value, None)
    else:
        normalized_default = default_value
        normalized_value = value
    
    if normalized_default and normalized_value == normalized_default:
        return "Default"
    return SOURCE_USER_INPUT


def _prompt_and_record_string(
    cli_value,
    prompt_text,
    default_value,
    summary_rows,
    config_key,
    *,
    normalizer=None,
    secret=False,
    required=False,
    cli_source="CLI Option",
):
    """Prompt for a string value and add to summary if provided."""
    if cli_value is not None:
        value = cli_value
        source = cli_source
    else:
        value = _collect_or_prompt_string(
            None,
            prompt=prompt_text,
            default=default_value,
            secret=secret,
            required=required,
            normalizer=normalizer,
        )
        if value is not None:
            source = _determine_value_source(value, default_value, normalizer)
        else:
            return None
    
    if value and value not in (None, ""):
        display_value = format_config_value(config_key, value, log_file_key=LOGGING_FILE_KEY)
        summary_rows.append((config_key, display_value, source))
    return value


def _prompt_and_record_bool(
    cli_value,
    prompt_text,
    default_value,
    summary_rows,
    config_key,
):
    """Prompt for a boolean value and add to summary."""
    if cli_value is not None:
        value = cli_value
        source = "CLI Option"
    else:
        value = _prompt_bool(prompt_text, default=default_value)
        source = "Default" if value == default_value else SOURCE_USER_INPUT
    
    display_value = format_config_value(config_key, value, log_file_key=LOGGING_FILE_KEY)
    summary_rows.append((config_key, display_value, source))
    return value


def _check_overwrite_destination(
    destination: Path, overwrite: bool, stdout_console: Console
):
    """Check if destination exists and handle overwrite logic."""
    if not destination.exists():
        return
    
    if overwrite:
        stdout_console.print(
            f"[yellow]Overwriting existing configuration at[/yellow] {destination}"
        )
    else:
        stdout_console.print(f"[yellow]{destination} already exists.[/yellow]")
        if not typer.confirm("Overwrite this file?", default=False):
            stdout_console.print(
                "[red]Aborted without changing the existing configuration.[/red]"
            )
            raise typer.Exit(code=1)


def _display_config_preview(
    summary_rows: list[tuple[str, str, str]], stdout_console: Console
):
    """Display configuration preview table."""
    if not summary_rows:
        return
    
    summary_rows.sort(key=lambda entry: entry[0])
    preview = Table(title="Local configuration preview")
    preview.add_column("Config Key", style=RichStyles.ACCENT)
    preview.add_column("Value", style=RichStyles.SECONDARY)
    preview.add_column("Source", style=RichStyles.SUCCESS)
    for dotted_key, display_value, source in summary_rows:
        preview.add_row(dotted_key, display_value, source)
    stdout_console.print()
    stdout_console.print(preview)



def _collect_config_file_entries(
    files: Sequence[Path],
) -> dict[str, tuple[Any, str]]:
    """Collect all config entries from files with their source filenames."""
    result: dict[str, tuple[Any, str]] = {}
    for file in files:
        if not file.exists():
            continue
        try:
            parsed = parse_toml_file(file, param_hint="--config")
        except typer.BadParameter:
            continue
        
        dotted = flatten_to_dotted(parsed)
        for key, value in dotted.items():
            if key not in result:
                result[key] = (value, file.name)
    return result


def _collect_cli_override_values(invocation: CliInvocation) -> dict[str, Any]:
    """Extract all CLI override values from invocation."""
    details: dict[str, Any] = {}
    if invocation.auth.api_key:
        details[BITSIGHT_API_KEY_KEY] = invocation.auth.api_key
    if invocation.subscription.folder:
        details[BITSIGHT_SUBSCRIPTION_FOLDER_KEY] = (
            invocation.subscription.folder
        )
    if invocation.subscription.type:
        details[BITSIGHT_SUBSCRIPTION_TYPE_KEY] = invocation.subscription.type
    if invocation.runtime.context:
        details[ROLE_CONTEXT_KEY] = invocation.runtime.context
    if invocation.runtime.risk_vector_filter:
        details[ROLE_RISK_VECTOR_FILTER_KEY] = (
            invocation.runtime.risk_vector_filter
        )
    if invocation.runtime.max_findings is not None:
        details[ROLE_MAX_FINDINGS_KEY] = invocation.runtime.max_findings
    if invocation.runtime.debug is not None:
        details[RUNTIME_DEBUG_KEY] = invocation.runtime.debug
    if invocation.runtime.skip_startup_checks is not None:
        details[RUNTIME_SKIP_STARTUP_CHECKS_KEY] = (
            invocation.runtime.skip_startup_checks
        )
    if invocation.tls.allow_insecure is not None:
        details[RUNTIME_ALLOW_INSECURE_TLS_KEY] = (
            invocation.tls.allow_insecure
        )
    if invocation.tls.ca_bundle_path:
        details[RUNTIME_CA_BUNDLE_PATH_KEY] = invocation.tls.ca_bundle_path
    if invocation.logging.level:
        details[LOGGING_LEVEL_KEY] = invocation.logging.level
    if invocation.logging.format:
        details[LOGGING_FORMAT_KEY] = invocation.logging.format
    if invocation.logging.file_path is not None:
        details[LOGGING_FILE_KEY] = invocation.logging.file_path
    if invocation.logging.max_bytes is not None:
        details[LOGGING_MAX_BYTES_KEY] = invocation.logging.max_bytes
    if invocation.logging.backup_count is not None:
        details[LOGGING_BACKUP_COUNT_KEY] = invocation.logging.backup_count
    return details


def _build_cli_source_labels(invocation: CliInvocation) -> dict[str, str]:
    """Build source labels for CLI overrides."""
    labels: dict[str, str] = {}
    if invocation.auth.api_key:
        labels[BITSIGHT_API_KEY_KEY] = "CLI"
    if invocation.subscription.folder:
        labels[BITSIGHT_SUBSCRIPTION_FOLDER_KEY] = "CLI"
    if invocation.subscription.type:
        labels[BITSIGHT_SUBSCRIPTION_TYPE_KEY] = "CLI"
    if invocation.runtime.context:
        labels[ROLE_CONTEXT_KEY] = "CLI"
    if invocation.runtime.risk_vector_filter:
        labels[ROLE_RISK_VECTOR_FILTER_KEY] = "CLI"
    if invocation.runtime.max_findings is not None:
        labels[ROLE_MAX_FINDINGS_KEY] = "CLI"
    if invocation.runtime.debug is not None:
        labels[RUNTIME_DEBUG_KEY] = "CLI"
    if invocation.runtime.skip_startup_checks is not None:
        labels[RUNTIME_SKIP_STARTUP_CHECKS_KEY] = "CLI"
    if invocation.tls.allow_insecure is not None:
        labels[RUNTIME_ALLOW_INSECURE_TLS_KEY] = "CLI"
    if invocation.tls.ca_bundle_path:
        labels[RUNTIME_CA_BUNDLE_PATH_KEY] = "CLI"
    if invocation.logging.level:
        labels[LOGGING_LEVEL_KEY] = "CLI"
    if invocation.logging.format:
        labels[LOGGING_FORMAT_KEY] = "CLI"
    if invocation.logging.file_path is not None:
        labels[LOGGING_FILE_KEY] = "CLI"
    if invocation.logging.max_bytes is not None:
        labels[LOGGING_MAX_BYTES_KEY] = "CLI"
    if invocation.logging.backup_count is not None:
        labels[LOGGING_BACKUP_COUNT_KEY] = "CLI"
    return labels


def _build_env_source_labels(env_overrides: Mapping[str, str]) -> dict[str, str]:
    """Build source labels for environment variable overrides."""
    from birre.config.settings import ENVVAR_TO_SETTINGS_KEY

    labels: dict[str, str] = {}
    for env_var in env_overrides:
        config_key = ENVVAR_TO_SETTINGS_KEY.get(env_var)
        if config_key:
            labels[config_key] = f"ENV ({env_var})"
    return labels


def _build_cli_override_rows(
    invocation: CliInvocation,
) -> Sequence[tuple[str, str, str]]:
    """Build table rows for CLI overrides."""
    rows: list[tuple[str, str, str]] = []
    for key, value in _collect_cli_override_values(invocation).items():
        rows.append((key, format_config_value(key, value, log_file_key=LOGGING_FILE_KEY), "CLI"))
    return rows


def _build_env_override_rows(
    env_overrides: Mapping[str, str],
) -> Sequence[tuple[str, str, str]]:
    """Build table rows for environment variable overrides."""
    from birre.config.settings import ENVVAR_TO_SETTINGS_KEY

    rows: list[tuple[str, str, str]] = []
    for env_var, value in env_overrides.items():
        config_key = ENVVAR_TO_SETTINGS_KEY.get(env_var)
        if not config_key:
            continue
        formatted_value = format_config_value(
            config_key, value, log_file_key=LOGGING_FILE_KEY
        )
        rows.append((config_key, formatted_value, f"ENV ({env_var})"))
    return rows


_EFFECTIVE_CONFIG_KEY_ORDER: tuple[str, ...] = (
    BITSIGHT_API_KEY_KEY,
    BITSIGHT_SUBSCRIPTION_FOLDER_KEY,
    BITSIGHT_SUBSCRIPTION_TYPE_KEY,
    ROLE_CONTEXT_KEY,
    ROLE_RISK_VECTOR_FILTER_KEY,
    ROLE_MAX_FINDINGS_KEY,
    RUNTIME_DEBUG_KEY,
    RUNTIME_SKIP_STARTUP_CHECKS_KEY,
    RUNTIME_ALLOW_INSECURE_TLS_KEY,
    RUNTIME_CA_BUNDLE_PATH_KEY,
    LOGGING_LEVEL_KEY,
    LOGGING_FORMAT_KEY,
    LOGGING_FILE_KEY,
    LOGGING_MAX_BYTES_KEY,
    LOGGING_BACKUP_COUNT_KEY,
)


def _effective_configuration_values(
    runtime_settings, logging_settings
) -> dict[str, Any]:
    """Extract effective configuration values from resolved settings."""
    values: dict[str, Any] = {
        BITSIGHT_API_KEY_KEY: getattr(runtime_settings, "api_key", None),
        BITSIGHT_SUBSCRIPTION_FOLDER_KEY: getattr(
            runtime_settings, "subscription_folder", None
        ),
        BITSIGHT_SUBSCRIPTION_TYPE_KEY: getattr(
            runtime_settings, "subscription_type", None
        ),
        ROLE_CONTEXT_KEY: getattr(runtime_settings, "context", None),
        ROLE_RISK_VECTOR_FILTER_KEY: getattr(
            runtime_settings, "risk_vector_filter", None
        ),
        ROLE_MAX_FINDINGS_KEY: getattr(runtime_settings, "max_findings", None),
        RUNTIME_DEBUG_KEY: getattr(runtime_settings, "debug", None),
        RUNTIME_SKIP_STARTUP_CHECKS_KEY: getattr(
            runtime_settings, "skip_startup_checks", None
        ),
        RUNTIME_ALLOW_INSECURE_TLS_KEY: getattr(
            runtime_settings, "allow_insecure_tls", None
        ),
        RUNTIME_CA_BUNDLE_PATH_KEY: getattr(
            runtime_settings, "ca_bundle_path", None
        ),
        LOGGING_LEVEL_KEY: logging.getLevelName(
            getattr(logging_settings, "level", logging.INFO)
        ),
        LOGGING_FORMAT_KEY: getattr(logging_settings, "format", None),
        LOGGING_FILE_KEY: getattr(logging_settings, "file_path", None),
        LOGGING_MAX_BYTES_KEY: getattr(logging_settings, "max_bytes", None),
        LOGGING_BACKUP_COUNT_KEY: getattr(
            logging_settings, "backup_count", None
        ),
    }
    return values


def _determine_source_label(
    key: str,
    cli_labels: Mapping[str, str],
    env_labels: Mapping[str, str],
    config_entries: Mapping[str, tuple[Any, str]],
) -> str:
    """Determine the source label for a config key."""
    if key in cli_labels:
        return cli_labels[key]
    if key in env_labels:
        return env_labels[key]
    if key in config_entries:
        return f"Config File ({config_entries[key][1]})"
    return "Default"


def _print_config_table(
    title: str,
    rows: Sequence[tuple[str, str, str]],
    stdout_console: Console,
) -> None:
    """Print a formatted config table."""
    table = create_config_table(title)
    table.columns[1].overflow = "fold"  # Set overflow for value column
    for key, value, source in rows:
        table.add_row(key, value, source)
    stdout_console.print(table)


def register(
    app: typer.Typer,
    *,
    stdout_console: Console,
) -> None:
    """Register config commands with the app."""

    # Config subcommands group
    config_app = typer.Typer(
        help="Manage BiRRe configuration files and settings.",
        invoke_without_command=True,
        no_args_is_help=True,
    )
    app.add_typer(config_app, name="config")

    @config_app.callback(invoke_without_command=True)
    def config_group_callback(ctx: typer.Context) -> None:
        """Display help when config group is invoked without a subcommand."""
        if ctx.invoked_subcommand is None:
            typer.echo(ctx.get_help())
            raise typer.Exit()

    @config_app.command(
        "init",
        help="Interactively create or update a local BiRRe configuration file.",
    )
    def config_init(
        output: cli_options.LocalConfOutputOption = Path(LOCAL_CONFIG_FILENAME),
        config_path: cli_options.ConfigPathOption = Path(LOCAL_CONFIG_FILENAME),
        subscription_type: cli_options.SubscriptionTypeOption = None,
        debug: cli_options.DebugOption = None,
        overwrite: cli_options.OverwriteOption = False,
    ) -> None:
        """Guide the user through generating a configuration file."""

        ctx = click.get_current_context()
        config_source = ctx.get_parameter_source("config_path")
        destination = Path(
            config_path
            if config_source is ParameterSource.COMMANDLINE
            else output
        )

        _check_overwrite_destination(destination, overwrite, stdout_console)

        defaults_settings = load_settings(
            str(config_path)
            if config_source is ParameterSource.COMMANDLINE
            else None
        )
        default_subscription_folder = defaults_settings.get(
            BITSIGHT_SUBSCRIPTION_FOLDER_KEY
        )
        default_subscription_type = defaults_settings.get(
            BITSIGHT_SUBSCRIPTION_TYPE_KEY
        )
        default_context = defaults_settings.get(ROLE_CONTEXT_KEY, "standard")
        default_debug = bool(defaults_settings.get(RUNTIME_DEBUG_KEY, False))

        summary_rows: list[tuple[str, str, str]] = []

        stdout_console.print("[bold]BiRRe local configuration generator[/bold]")

        api_key = _collect_or_prompt_string(
            None,
            prompt="BitSight API key",
            default=None,
            secret=True,
            required=True,
        )
        if api_key:
            display_value = format_config_value(
                BITSIGHT_API_KEY_KEY, api_key, log_file_key=LOGGING_FILE_KEY
            )
            summary_rows.append(
                (BITSIGHT_API_KEY_KEY, display_value, SOURCE_USER_INPUT)
            )

        subscription_folder = _prompt_and_record_string(
            None,
            "Default subscription folder",
            (
                str(default_subscription_folder)
                if default_subscription_folder
                else ""
            ),
            summary_rows,
            BITSIGHT_SUBSCRIPTION_FOLDER_KEY,
        )

        subscription_type_value = _prompt_and_record_string(
            subscription_type,
            "Default subscription type",
            str(default_subscription_type) if default_subscription_type else "",
            summary_rows,
            BITSIGHT_SUBSCRIPTION_TYPE_KEY,
        )

        context_value = _prompt_and_record_string(
            None,
            "Default persona (standard or risk_manager)",
            str(default_context or "standard"),
            summary_rows,
            ROLE_CONTEXT_KEY,
            normalizer=lambda value, _: cli_options.normalize_context(
                value, choices=CONTEXT_CHOICES
            ),
        )

        debug_value = _prompt_and_record_bool(
            debug,
            "Enable debug mode?",
            default_debug,
            summary_rows,
            RUNTIME_DEBUG_KEY,
        )

        generated = {
            "bitsight": {
                "api_key": api_key,
                "subscription_folder": subscription_folder,
                "subscription_type": subscription_type_value,
            },
            "runtime": {
                "debug": debug_value,
            },
            "roles": {
                "context": context_value,
            },
        }

        serializable: dict[str, dict[str, Any]] = {}
        for section, section_values in generated.items():
            filtered = {k: v for k, v in section_values.items() if v not in (None, "")}
            if filtered:
                serializable[section] = filtered

        if not serializable:
            stdout_console.print(
                "[red]No values provided; aborting local configuration generation.[/red]"
            )
            raise typer.Exit(code=1)

        _display_config_preview(summary_rows, stdout_console)

        content = _generate_local_config_content(serializable)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            destination.write_text(content, encoding="utf-8")
        except OSError as error:
            stdout_console.print(
                f"[red]Failed to write configuration:[/red] {error}"
            )
            raise typer.Exit(code=1) from error

        stdout_console.print(
            f"[green]Local configuration saved to[/green] {destination}"
        )

    @config_app.command(
        "show",
        help=(
            "Inspect configuration sources and resolved settings.\n\n"
            "Example: uv run birre config show --config custom.toml"
        ),
    )
    def config_show(  # NOSONAR python:S107
        config: cli_options.ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),
        bitsight_api_key: cli_options.BitsightApiKeyOption = None,
        subscription_folder: cli_options.SubscriptionFolderOption = None,
        subscription_type: cli_options.SubscriptionTypeOption = None,
        context: cli_options.ContextOption = None,
        debug: cli_options.DebugOption = None,
        allow_insecure_tls: cli_options.AllowInsecureTlsOption = None,
        ca_bundle: cli_options.CaBundleOption = None,
        risk_vector_filter: cli_options.RiskVectorFilterOption = None,
        max_findings: cli_options.MaxFindingsOption = None,
        log_level: cli_options.LogLevelOption = None,
        log_format: cli_options.LogFormatOption = None,
        log_file: cli_options.LogFileOption = None,
        log_max_bytes: cli_options.LogMaxBytesOption = None,
        log_backup_count: cli_options.LogBackupCountOption = None,
    ) -> None:
        """Display configuration files, overrides, and effective values."""
        invocation = build_invocation(
            config_path=str(config) if config is not None else None,
            api_key=bitsight_api_key,
            subscription_folder=subscription_folder,
            subscription_type=subscription_type,
            context=context,
            debug=debug,
            risk_vector_filter=risk_vector_filter,
            max_findings=max_findings,
            skip_startup_checks=None,
            allow_insecure_tls=allow_insecure_tls,
            ca_bundle=ca_bundle,
            log_level=log_level,
            log_format=log_format,
            log_file=log_file,
            log_max_bytes=log_max_bytes,
            log_backup_count=log_backup_count,
        )

        runtime_settings, logging_settings, _ = resolve_runtime_and_logging(
            invocation
        )
        files = resolve_config_file_candidates(invocation.config_path)

        config_entries = _collect_config_file_entries(files)

        files_table = Table(title="Configuration files", box=box.SIMPLE_HEAVY)
        files_table.add_column("File", style=RichStyles.ACCENT)
        files_table.add_column("Status", style=RichStyles.SECONDARY)
        for file in files:
            status = "exists" if file.exists() else "missing"
            files_table.add_row(str(file), status)
        stdout_console.print(files_table)

        env_overrides = {
            name: os.getenv(name)
            for name in (
                "BIRRE_CONFIG",
                "BITSIGHT_API_KEY",
                "BIRRE_SUBSCRIPTION_FOLDER",
                "BIRRE_SUBSCRIPTION_TYPE",
                "BIRRE_CONTEXT",
                "BIRRE_RISK_VECTOR_FILTER",
                "BIRRE_MAX_FINDINGS",
                "BIRRE_SKIP_STARTUP_CHECKS",
                "BIRRE_DEBUG",
                "BIRRE_ALLOW_INSECURE_TLS",
                "BIRRE_CA_BUNDLE",
                "BIRRE_LOG_LEVEL",
                "BIRRE_LOG_FORMAT",
                "BIRRE_LOG_FILE",
                "BIRRE_LOG_MAX_BYTES",
                "BIRRE_LOG_BACKUP_COUNT",
            )
            if os.getenv(name) is not None
        }
        env_labels = _build_env_source_labels(env_overrides)
        env_rows = list(_build_env_override_rows(env_overrides))
        if env_rows:
            stdout_console.print()
            _print_config_table("Environment overrides", env_rows, stdout_console)

        cli_labels = {
            key: label
            for key, label in _build_cli_source_labels(invocation).items()
            if key not in env_labels
        }
        cli_rows = [
            row
            for row in _build_cli_override_rows(invocation)
            if row[0] not in env_labels
        ]
        if cli_rows:
            stdout_console.print()
            _print_config_table("CLI overrides", cli_rows, stdout_console)

        effective_values = _effective_configuration_values(
            runtime_settings, logging_settings
        )
        effective_rows: list[tuple[str, str, str]] = []
        for key in _EFFECTIVE_CONFIG_KEY_ORDER:
            display_value = format_config_value(
                key, effective_values.get(key), log_file_key=LOGGING_FILE_KEY
            )
            source_label = _determine_source_label(
                key, cli_labels, env_labels, config_entries
            )
            effective_rows.append((key, display_value, source_label))

        stdout_console.print()
        _print_config_table("Effective configuration", effective_rows, stdout_console)

    @config_app.command(
        "validate",
        help="Validate or minimize a BiRRe configuration file before use.",
    )
    def config_validate(
        config: Path | None = typer.Option(
            None,
            "--config",
            help="Configuration TOML file to validate",
            envvar="BIRRE_CONFIG",
            show_envvar=True,
            rich_help_panel="Configuration",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
        debug: cli_options.DebugOption = None,
        minimize: cli_options.MinimizeOption = False,
    ) -> None:
        """Validate configuration syntax and optionally rewrite it in minimal form."""
        ctx = click.get_current_context()
        config_source = ctx.get_parameter_source("config")
        if config is None and config_source is ParameterSource.DEFAULT:
            typer.echo(ctx.get_help())
            raise typer.Exit()
        
        # Validate config file exists and is valid TOML
        config = require_file_exists(config, param_hint="--config")
        parsed = parse_toml_file(config, param_hint="--config")

        allowed_sections = {"bitsight", "runtime", "roles", "logging"}
        warnings: list[str] = []
        for section in parsed:
            if section not in allowed_sections:
                warnings.append(
                    f"Unknown section '{section}' will be ignored by BiRRe"
                )

        stdout_console.print(f"[green]TOML parsing succeeded[/green] for {config}")
        if warnings:
            stdout_console.print("[yellow]Warnings:[/yellow]")
            for warning in warnings:
                stdout_console.print(f"- {warning}")

        if debug:
            stdout_console.print("\n[bold]Parsed data[/bold]")
            stdout_console.print(parsed)

        if minimize:
            minimized = _generate_local_config_content(parsed, include_header=False)
            backup_path = config.with_suffix(f"{config.suffix}.bak")
            shutil.copy2(config, backup_path)
            config.write_text(minimized, encoding="utf-8")
            stdout_console.print(
                f"[green]Minimized configuration written to[/green] {config} "
                f"[dim](backup: {backup_path})[/dim]"
            )
