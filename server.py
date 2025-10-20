"""BiRRe FastMCP server entrypoint."""

import asyncio
import inspect
import logging
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import typer
from rich.console import Console
from typing_extensions import Annotated
from typer.main import get_command

# FastMCP checks this flag during import time, so ensure it is enabled before
# importing any modules that depend on FastMCP.
os.environ["FASTMCP_EXPERIMENTAL_ENABLE_NEW_OPENAPI_PARSER"] = "true"

from src.birre import create_birre_server
from src.constants import DEFAULT_CONFIG_FILENAME
from src.logging import configure_logging, get_logger
from src.settings import (
    LoggingInputs,
    RuntimeInputs,
    SubscriptionInputs,
    TlsInputs,
    apply_cli_overrides,
    load_settings,
    logging_from_settings,
    runtime_from_settings,
)
from src.startup_checks import run_offline_startup_checks, run_online_startup_checks

console = Console(stderr=True)

app = typer.Typer(
    help="Run the BiRRe FastMCP server",
    rich_markup_mode="rich",
)

_CLI_PROG_NAME = Path(__file__).name
_CONTEXT_CHOICES = {"standard", "risk_manager"}
_LOG_FORMAT_CHOICES = {"text", "json"}
_LOG_LEVEL_CHOICES = sorted(
    name
    for name, value in logging.getLevelNamesMapping().items()
    if isinstance(name, str) and not name.isdigit()
)
_LOG_LEVEL_SET = {choice.upper() for choice in _LOG_LEVEL_CHOICES}


def _banner() -> str:
    return (
        "\n"
        "╭────────────────────────────────────────────────────────────────╮\n"
        "│\033[0;33m                                                                \033[0m│\n"
        "│\033[0;33m     ███████████   ███  ███████████   ███████████               \033[0m│\n"
        "│\033[0;33m    ░░███░░░░░███ ░░░  ░░███░░░░░███ ░░███░░░░░███              \033[0m│\n"
        "│\033[0;33m     ░███    ░███ ████  ░███    ░███  ░███    ░███   ██████     \033[0m│\n"
        "│\033[0;33m     ░██████████ ░░███  ░██████████   ░██████████   ███░░███    \033[0m│\n"
        "│\033[0;33m     ░███░░░░░███ ░███  ░███░░░░░███  ░███░░░░░███ ░███████     \033[0m│\n"
        "│\033[0;33m     ░███    ░███ ░███  ░███    ░███  ░███    ░███ ░███░░░      \033[0m│\n"
        "│\033[0;33m     ███████████  █████ █████   █████ █████   █████░░██████     \033[0m│\n"
        "│\033[0;33m    ░░░░░░░░░░░  ░░░░░ ░░░░░   ░░░░░ ░░░░░   ░░░░░  ░░░░░░      \033[0m│\n"
        "│\033[0;33m                                                                \033[0m│\n"
        "│\033[2m                   Bitsight Rating Retriever                    \033[0m│\n"
        "│\033[0;33m                 Model Context Protocol Server                  \033[0m│\n"
        "│\033[0;33m                https://github.com/boecht/birre                 \033[0m│\n"
        "╰────────────────────────────────────────────────────────────────╯\n\033[0m"
    )


def _keyboard_interrupt_banner() -> str:
    return (
        "\n"
        "╭────────────────────────────────────────╮\n"
        "│\033[0;31m  Keyboard interrupt received — stopping  \033[0m│\n"
        "│\033[0;31m          BiRRe FastMCP server            \033[0m│\n"
        "╰────────────────────────────────────────╯\n\033[0m"
    )


def _normalize_context(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    candidate = value.strip().lower().replace("-", "_")
    if not candidate:
        return None
    if candidate not in _CONTEXT_CHOICES:
        raise typer.BadParameter(
            f"Context must be one of: {', '.join(sorted(_CONTEXT_CHOICES))}",
            param_hint="--context",
        )
    return candidate


def _normalize_log_format(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    candidate = value.strip().lower()
    if not candidate:
        return None
    if candidate not in _LOG_FORMAT_CHOICES:
        raise typer.BadParameter(
            "Log format must be either 'text' or 'json'",
            param_hint="--log-format",
        )
    return candidate


def _normalize_log_level(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    candidate = value.strip().upper()
    if not candidate:
        return None
    if candidate not in _LOG_LEVEL_SET:
        raise typer.BadParameter(
            f"Log level must be one of: {', '.join(_LOG_LEVEL_CHOICES)}",
            param_hint="--log-level",
        )
    return candidate


ApiKeyOption = Annotated[
    Optional[str],
    typer.Option(
        "--bitsight-api-key",
        help="BitSight API key (overrides BITSIGHT_API_KEY env var)",
        envvar="BITSIGHT_API_KEY",
        show_envvar=True,
        rich_help_panel="Authentication",
    ),
]
ConfigPathOption = Annotated[
    str,
    typer.Option(
        "--config",
        help="Path to BiRRe config TOML",
        show_default=True,
        rich_help_panel="Configuration",
    ),
]
ContextOption = Annotated[
    Optional[str],
    typer.Option(
        "--context",
        help="Tool persona to expose (standard or risk_manager)",
        envvar="BIRRE_CONTEXT",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]
LogLevelOption = Annotated[
    Optional[str],
    typer.Option(
        "--log-level",
        help="Logging level (defaults to INFO unless overridden)",
        envvar="BIRRE_LOG_LEVEL",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]
LogFormatOption = Annotated[
    Optional[str],
    typer.Option(
        "--log-format",
        help="Logging format (text or json)",
        envvar="BIRRE_LOG_FORMAT",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]
LogFileOption = Annotated[
    Optional[str],
    typer.Option(
        "--log-file",
        help="Log file path (adds rotating file handler)",
        envvar="BIRRE_LOG_FILE",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]
LogMaxBytesOption = Annotated[
    Optional[int],
    typer.Option(
        "--log-max-bytes",
        help="Maximum size in bytes for rotating log files",
        envvar="BIRRE_LOG_MAX_BYTES",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]
LogBackupCountOption = Annotated[
    Optional[int],
    typer.Option(
        "--log-backup-count",
        help="Number of rotating log file backups to keep",
        envvar="BIRRE_LOG_BACKUP_COUNT",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]
SkipStartupChecksOption = Annotated[
    Optional[bool],
    typer.Option(
        "--skip-startup-checks/--no-skip-startup-checks",
        help="Skip BitSight startup checks (not recommended)",
        envvar="BIRRE_SKIP_STARTUP_CHECKS",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]
SubscriptionFolderOption = Annotated[
    Optional[str],
    typer.Option(
        "--subscription-folder",
        help="Preferred BitSight subscription folder name (e.g. API), must exist",
        envvar="BIRRE_SUBSCRIPTION_FOLDER",
        show_envvar=True,
        rich_help_panel="BitSight",
    ),
]
SubscriptionTypeOption = Annotated[
    Optional[str],
    typer.Option(
        "--subscription-type",
        help="BitSight subscription type (e.g. continuous_monitoring)",
        envvar="BIRRE_SUBSCRIPTION_TYPE",
        show_envvar=True,
        rich_help_panel="BitSight",
    ),
]
RiskVectorFilterOption = Annotated[
    Optional[str],
    typer.Option(
        "--risk-vector-filter",
        help="Override the default risk vectors used for top findings (comma-separated).",
        envvar="BIRRE_RISK_VECTOR_FILTER",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]
MaxFindingsOption = Annotated[
    Optional[int],
    typer.Option(
        "--max-findings",
        help="Maximum number of findings/details to surface per company (default: 10).",
        envvar="BIRRE_MAX_FINDINGS",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]
DebugOption = Annotated[
    Optional[bool],
    typer.Option(
        "--debug/--no-debug",
        help="Enable verbose debug logging and diagnostic payloads",
        envvar="BIRRE_DEBUG",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]
AllowInsecureTlsOption = Annotated[
    Optional[bool],
    typer.Option(
        "--allow-insecure-tls/--require-secure-tls",
        help=(
            "Disable HTTPS certificate verification for BitSight API requests. "
            "Use only when behind a trusted intercepting proxy."
        ),
        envvar="BIRRE_ALLOW_INSECURE_TLS",
        show_envvar=True,
        rich_help_panel="TLS",
    ),
]
CaBundleOption = Annotated[
    Optional[str],
    typer.Option(
        "--ca-bundle",
        help=(
            "Path to a custom CA bundle for BitSight API HTTPS verification "
            "(overrides system trust store)."
        ),
        envvar="BIRRE_CA_BUNDLE",
        show_envvar=True,
        rich_help_panel="TLS",
    ),
]


@dataclass(frozen=True)
class _LoggingCliOptions:
    level: Optional[str] = None
    format: Optional[str] = None
    file_path: Optional[str] = None
    max_bytes: Optional[int] = None
    backup_count: Optional[int] = None


@dataclass(frozen=True)
class _RuntimeCliOptions:
    context: Optional[str] = None
    debug: Optional[bool] = None
    risk_vector_filter: Optional[str] = None
    max_findings: Optional[int] = None
    skip_startup_checks: Optional[bool] = None


@dataclass(frozen=True)
class _SubscriptionCliOptions:
    folder: Optional[str] = None
    type: Optional[str] = None


@dataclass(frozen=True)
class _TlsCliOptions:
    allow_insecure: Optional[bool] = None
    ca_bundle_path: Optional[str] = None


def _run_server(
    *,
    api_key: Optional[str],
    config_path: str,
    logging_cli: _LoggingCliOptions,
    runtime_cli: _RuntimeCliOptions,
    subscription_cli: _SubscriptionCliOptions,
    tls_cli: _TlsCliOptions,
    context_alias: Optional[str] = None,
) -> None:
    alias_context = _normalize_context(context_alias) if context_alias else None
    requested_context = _normalize_context(runtime_cli.context)
    if alias_context and requested_context and alias_context != requested_context:
        raise typer.BadParameter(
            f"Context '{requested_context}' conflicts with the '{alias_context}' command.",
            param_hint="--context",
        )
    normalized_context = alias_context or requested_context

    normalized_log_format = _normalize_log_format(logging_cli.format)
    normalized_log_level = _normalize_log_level(logging_cli.level)

    logging_inputs = LoggingInputs(
        level=normalized_log_level,
        format=normalized_log_format,
        file_path=logging_cli.file_path,
        max_bytes=logging_cli.max_bytes,
        backup_count=logging_cli.backup_count,
    )
    runtime_inputs = RuntimeInputs(
        context=normalized_context,
        debug=runtime_cli.debug,
        risk_vector_filter=runtime_cli.risk_vector_filter,
        max_findings=runtime_cli.max_findings,
        skip_startup_checks=runtime_cli.skip_startup_checks,
    )
    subscription_inputs = SubscriptionInputs(
        folder=subscription_cli.folder,
        type=subscription_cli.type,
    )
    tls_inputs = TlsInputs(
        allow_insecure=tls_cli.allow_insecure,
        ca_bundle_path=tls_cli.ca_bundle_path,
    )

    config_settings = load_settings(config_path)
    apply_cli_overrides(
        config_settings,
        api_key_input=api_key,
        subscription_inputs=subscription_inputs,
        runtime_inputs=runtime_inputs,
        tls_inputs=tls_inputs,
        logging_inputs=logging_inputs,
    )

    runtime_settings = runtime_from_settings(config_settings)
    logging_settings = logging_from_settings(config_settings)
    if runtime_settings["debug"] and logging_settings.level > logging.DEBUG:
        logging_settings = replace(logging_settings, level=logging.DEBUG)

    console.print(_banner(), markup=False)

    configure_logging(logging_settings)
    logger = get_logger("birre")

    for message in runtime_settings.get("overrides", []):
        logger.info(message)

    for message in runtime_settings.get("warnings", []):
        logger.warning(message)

    logger.info("Running offline startup checks")
    offline_ok = run_offline_startup_checks(
        has_api_key=bool(runtime_settings["api_key"]),  # CodeQL false positive
        subscription_folder=runtime_settings["subscription_folder"],
        subscription_type=runtime_settings["subscription_type"],
        logger=logger,
    )
    if not offline_ok:
        logger.critical("Offline startup checks failed; aborting startup")
        raise SystemExit(1)

    logger.info("Preparing BiRRe FastMCP server")
    server = create_birre_server(settings=runtime_settings, logger=logger)

    logger.info("Running online startup checks")
    skip_checks = (
        runtime_cli.skip_startup_checks
        if runtime_cli.skip_startup_checks is not None
        else runtime_settings["skip_startup_checks"]
    )
    call_v1_tool = getattr(server, "call_v1_tool", None)
    online_ok = asyncio.run(
        run_online_startup_checks(
            call_v1_tool=call_v1_tool,
            subscription_folder=runtime_settings["subscription_folder"],
            subscription_type=runtime_settings["subscription_type"],
            logger=logger,
            skip_startup_checks=skip_checks,
        )
    )
    if not online_ok:
        logger.critical("Online startup checks failed; aborting startup")
        raise SystemExit(1)

    logger.info("Starting BiRRe FastMCP server")
    try:
        server.run()
    except KeyboardInterrupt:
        console.print(_keyboard_interrupt_banner(), markup=False)
        logger.info("BiRRe FastMCP server stopped via KeyboardInterrupt")


@app.command(help="Serve BiRRe with an explicitly selected context.")
def serve(
    api_key: ApiKeyOption = None,
    config_path: ConfigPathOption = DEFAULT_CONFIG_FILENAME,
    context: ContextOption = None,
    log_level: LogLevelOption = None,
    log_format: LogFormatOption = None,
    log_file: LogFileOption = None,
    log_max_bytes: LogMaxBytesOption = None,
    log_backup_count: LogBackupCountOption = None,
    skip_startup_checks: SkipStartupChecksOption = None,
    subscription_folder: SubscriptionFolderOption = None,
    subscription_type: SubscriptionTypeOption = None,
    risk_vector_filter: RiskVectorFilterOption = None,
    max_findings: MaxFindingsOption = None,
    debug: DebugOption = None,
    allow_insecure_tls: AllowInsecureTlsOption = None,
    ca_bundle_path: CaBundleOption = None,
) -> None:
    """Run the BiRRe FastMCP server."""

    _run_server(
        api_key=api_key,
        config_path=config_path,
        logging_cli=_LoggingCliOptions(
            level=log_level,
            format=log_format,
            file_path=log_file,
            max_bytes=log_max_bytes,
            backup_count=log_backup_count,
        ),
        runtime_cli=_RuntimeCliOptions(
            context=context,
            debug=debug,
            risk_vector_filter=risk_vector_filter,
            max_findings=max_findings,
            skip_startup_checks=skip_startup_checks,
        ),
        subscription_cli=_SubscriptionCliOptions(
            folder=subscription_folder,
            type=subscription_type,
        ),
        tls_cli=_TlsCliOptions(
            allow_insecure=allow_insecure_tls,
            ca_bundle_path=ca_bundle_path,
        ),
    )


@app.command(help="Serve BiRRe using the standard tool persona.")
def standard(
    api_key: ApiKeyOption = None,
    config_path: ConfigPathOption = DEFAULT_CONFIG_FILENAME,
    log_level: LogLevelOption = None,
    log_format: LogFormatOption = None,
    log_file: LogFileOption = None,
    log_max_bytes: LogMaxBytesOption = None,
    log_backup_count: LogBackupCountOption = None,
    skip_startup_checks: SkipStartupChecksOption = None,
    subscription_folder: SubscriptionFolderOption = None,
    subscription_type: SubscriptionTypeOption = None,
    risk_vector_filter: RiskVectorFilterOption = None,
    max_findings: MaxFindingsOption = None,
    debug: DebugOption = None,
    allow_insecure_tls: AllowInsecureTlsOption = None,
    ca_bundle_path: CaBundleOption = None,
) -> None:
    """Run the BiRRe FastMCP server in the standard context."""

    _run_server(
        api_key=api_key,
        config_path=config_path,
        logging_cli=_LoggingCliOptions(
            level=log_level,
            format=log_format,
            file_path=log_file,
            max_bytes=log_max_bytes,
            backup_count=log_backup_count,
        ),
        runtime_cli=_RuntimeCliOptions(
            context=None,
            debug=debug,
            risk_vector_filter=risk_vector_filter,
            max_findings=max_findings,
            skip_startup_checks=skip_startup_checks,
        ),
        subscription_cli=_SubscriptionCliOptions(
            folder=subscription_folder,
            type=subscription_type,
        ),
        tls_cli=_TlsCliOptions(
            allow_insecure=allow_insecure_tls,
            ca_bundle_path=ca_bundle_path,
        ),
        context_alias="standard",
    )


def _risk_manager_command(**options: Any) -> None:
    """Implementation for the risk manager persona command."""

    option_map: Mapping[str, Any] = options
    _run_server(
        api_key=option_map.get("api_key"),
        config_path=option_map.get("config_path", DEFAULT_CONFIG_FILENAME),
        logging_cli=_LoggingCliOptions(
            level=option_map.get("log_level"),
            format=option_map.get("log_format"),
            file_path=option_map.get("log_file"),
            max_bytes=option_map.get("log_max_bytes"),
            backup_count=option_map.get("log_backup_count"),
        ),
        runtime_cli=_RuntimeCliOptions(
            context=None,
            debug=option_map.get("debug"),
            risk_vector_filter=option_map.get("risk_vector_filter"),
            max_findings=option_map.get("max_findings"),
            skip_startup_checks=option_map.get("skip_startup_checks"),
        ),
        subscription_cli=_SubscriptionCliOptions(
            folder=option_map.get("subscription_folder"),
            type=option_map.get("subscription_type"),
        ),
        tls_cli=_TlsCliOptions(
            allow_insecure=option_map.get("allow_insecure_tls"),
            ca_bundle_path=option_map.get("ca_bundle_path"),
        ),
        context_alias="risk_manager",
    )


_RISK_MANAGER_SIGNATURE = inspect.signature(standard)

_RISK_MANAGER_SIGNATURE_PARAMETERS = tuple(_RISK_MANAGER_SIGNATURE.parameters.values())


def _apply_signature(target: Any) -> None:
    target.__signature__ = _RISK_MANAGER_SIGNATURE.replace(
        parameters=_RISK_MANAGER_SIGNATURE_PARAMETERS
    )
    target.__annotations__ = getattr(standard, "__annotations__", {}).copy()


_apply_signature(_risk_manager_command)

risk_manager = app.command(
    "risk-manager", help="Serve BiRRe using the risk manager persona."
)(_risk_manager_command)
_apply_signature(risk_manager)
risk_manager.__doc__ = "Run the BiRRe FastMCP server in the risk manager context."


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Main entry point for BiRRe MCP server."""

    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        _run_server(
            api_key=None,
            config_path=DEFAULT_CONFIG_FILENAME,
            logging_cli=_LoggingCliOptions(),
            runtime_cli=_RuntimeCliOptions(),
            subscription_cli=_SubscriptionCliOptions(),
            tls_cli=_TlsCliOptions(),
        )
        return

    command = get_command(app)
    if args[0] in {"-h", "--help"}:
        command.main(args=args, prog_name=_CLI_PROG_NAME)
        return

    if args[0].startswith("-"):
        command.main(args=["serve", *args], prog_name=_CLI_PROG_NAME)
    else:
        command.main(args=args, prog_name=_CLI_PROG_NAME)


if __name__ == "__main__":
    main()
