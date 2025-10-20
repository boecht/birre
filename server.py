"""BiRRe FastMCP server entrypoint."""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, Optional, Sequence

import click
from rich.console import Console

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

app = click.Group(help="Run the BiRRe FastMCP server")

_CONTEXT_CHOICES = {"standard", "risk_manager"}
_LOG_FORMAT_CHOICES = {"text", "json"}
_LOG_LEVEL_CHOICES = sorted(
    name
    for name, value in logging.getLevelNamesMapping().items()
    if isinstance(name, str) and not name.isdigit()
)
_LOG_LEVEL_SET = {choice.upper() for choice in _LOG_LEVEL_CHOICES}
_PROG_NAME = "server.py"


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
        raise click.BadParameter(
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
        raise click.BadParameter(
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
        raise click.BadParameter(
            f"Log level must be one of: {', '.join(_LOG_LEVEL_CHOICES)}",
            param_hint="--log-level",
        )
    return candidate


@dataclass
class _CliOptions:
    api_key: Optional[str] = None
    config_path: str = DEFAULT_CONFIG_FILENAME
    context: Optional[str] = None
    log_level: Optional[str] = None
    log_format: Optional[str] = None
    log_file: Optional[str] = None
    log_max_bytes: Optional[int] = None
    log_backup_count: Optional[int] = None
    skip_startup_checks: Optional[bool] = None
    subscription_folder: Optional[str] = None
    subscription_type: Optional[str] = None
    risk_vector_filter: Optional[str] = None
    max_findings: Optional[int] = None
    debug: Optional[bool] = None
    allow_insecure_tls: Optional[bool] = None
    ca_bundle_path: Optional[str] = None


def _run_server(
    options: _CliOptions,
    *,
    context_alias: Optional[str] = None,
) -> None:
    alias_context = _normalize_context(context_alias) if context_alias else None
    requested_context = _normalize_context(options.context)
    if alias_context and requested_context and alias_context != requested_context:
        raise click.BadParameter(
            f"Context '{requested_context}' conflicts with the '{alias_context}' command.",
            param_hint="--context",
        )
    normalized_context = alias_context or requested_context

    normalized_log_format = _normalize_log_format(options.log_format)
    normalized_log_level = _normalize_log_level(options.log_level)

    logging_inputs = LoggingInputs(
        level=normalized_log_level,
        format=normalized_log_format,
        file_path=options.log_file,
        max_bytes=options.log_max_bytes,
        backup_count=options.log_backup_count,
    )
    runtime_inputs = RuntimeInputs(
        context=normalized_context,
        debug=options.debug,
        risk_vector_filter=options.risk_vector_filter,
        max_findings=options.max_findings,
        skip_startup_checks=options.skip_startup_checks,
    )
    subscription_inputs = SubscriptionInputs(
        folder=options.subscription_folder,
        type=options.subscription_type,
    )
    tls_inputs = TlsInputs(
        allow_insecure=options.allow_insecure_tls,
        ca_bundle_path=options.ca_bundle_path,
    )

    config_settings = load_settings(options.config_path)
    apply_cli_overrides(
        config_settings,
        api_key_input=options.api_key,
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
        options.skip_startup_checks
        if options.skip_startup_checks is not None
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


def _cli_option_decorators(include_context: bool) -> Sequence[Callable[[Any], Callable[[Any], Any]]]:
    options: list[Callable[[Any], Callable[[Any], Any]]] = [
        click.option(
            "--bitsight-api-key",
            "api_key",
            help="BitSight API key (overrides BITSIGHT_API_KEY env var)",
            envvar="BITSIGHT_API_KEY",
            show_envvar=True,
        ),
        click.option(
            "--config",
            "config_path",
            default=DEFAULT_CONFIG_FILENAME,
            show_default=True,
            help="Path to BiRRe config TOML",
        ),
    ]
    if include_context:
        options.append(
            click.option(
                "--context",
                "context",
                help="Tool persona to expose (standard or risk_manager)",
                envvar="BIRRE_CONTEXT",
                show_envvar=True,
            )
        )
    options.extend(
        [
            click.option(
                "--log-level",
                "log_level",
                help="Logging level (defaults to INFO unless overridden)",
                envvar="BIRRE_LOG_LEVEL",
                show_envvar=True,
            ),
            click.option(
                "--log-format",
                "log_format",
                help="Logging format (text or json)",
                envvar="BIRRE_LOG_FORMAT",
                show_envvar=True,
            ),
            click.option(
                "--log-file",
                "log_file",
                help="Log file path (adds rotating file handler)",
                envvar="BIRRE_LOG_FILE",
                show_envvar=True,
            ),
            click.option(
                "--log-max-bytes",
                "log_max_bytes",
                type=int,
                help="Maximum size in bytes for rotating log files",
                envvar="BIRRE_LOG_MAX_BYTES",
                show_envvar=True,
            ),
            click.option(
                "--log-backup-count",
                "log_backup_count",
                type=int,
                help="Number of rotating log file backups to keep",
                envvar="BIRRE_LOG_BACKUP_COUNT",
                show_envvar=True,
            ),
            click.option(
                "--skip-startup-checks/--no-skip-startup-checks",
                "skip_startup_checks",
                default=None,
                help="Skip BitSight startup checks (not recommended)",
                envvar="BIRRE_SKIP_STARTUP_CHECKS",
                show_envvar=True,
            ),
            click.option(
                "--subscription-folder",
                "subscription_folder",
                help="Preferred BitSight subscription folder name (e.g. API), must exist",
                envvar="BIRRE_SUBSCRIPTION_FOLDER",
                show_envvar=True,
            ),
            click.option(
                "--subscription-type",
                "subscription_type",
                help="BitSight subscription type (e.g. continuous_monitoring)",
                envvar="BIRRE_SUBSCRIPTION_TYPE",
                show_envvar=True,
            ),
            click.option(
                "--risk-vector-filter",
                "risk_vector_filter",
                help=(
                    "Override the default risk vectors used for top findings (comma-separated)."
                ),
                envvar="BIRRE_RISK_VECTOR_FILTER",
                show_envvar=True,
            ),
            click.option(
                "--max-findings",
                "max_findings",
                type=int,
                help="Maximum number of findings/details to surface per company (default: 10).",
                envvar="BIRRE_MAX_FINDINGS",
                show_envvar=True,
            ),
            click.option(
                "--debug/--no-debug",
                "debug",
                default=None,
                help="Enable verbose debug logging and diagnostic payloads",
                envvar="BIRRE_DEBUG",
                show_envvar=True,
            ),
            click.option(
                "--allow-insecure-tls/--require-secure-tls",
                "allow_insecure_tls",
                default=None,
                help=(
                    "Disable HTTPS certificate verification for BitSight API requests. "
                    "Use only when behind a trusted intercepting proxy."
                ),
                envvar="BIRRE_ALLOW_INSECURE_TLS",
                show_envvar=True,
            ),
            click.option(
                "--ca-bundle",
                "ca_bundle_path",
                help=(
                    "Path to a custom CA bundle for BitSight API HTTPS verification "
                    "(overrides system trust store)."
                ),
                envvar="BIRRE_CA_BUNDLE",
                show_envvar=True,
            ),
        ]
    )
    return options


def _apply_cli_options(include_context: bool) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(function: Callable[..., Any]) -> Callable[..., Any]:
        for option in reversed(_cli_option_decorators(include_context)):
            function = option(function)
        return function

    return decorator


def _execute_cli_command(cli_kwargs: Dict[str, Any], *, context_alias: Optional[str]) -> None:
    options = _CliOptions(**cli_kwargs)
    _run_server(options, context_alias=context_alias)


@app.command(help="Serve BiRRe with an explicitly selected context.")
@_apply_cli_options(include_context=True)
def serve(**cli_kwargs) -> None:
    """Run the BiRRe FastMCP server."""

    _execute_cli_command(dict(cli_kwargs), context_alias=None)


@app.command(help="Serve BiRRe using the standard tool persona.")
@_apply_cli_options(include_context=False)
def standard(**cli_kwargs) -> None:
    """Run the BiRRe FastMCP server in the standard context."""

    _execute_cli_command(dict(cli_kwargs), context_alias="standard")


@app.command("risk-manager", help="Serve BiRRe using the risk manager persona.")
@_apply_cli_options(include_context=False)
def risk_manager(**cli_kwargs) -> None:
    """Run the BiRRe FastMCP server in the risk manager context."""

    _execute_cli_command(dict(cli_kwargs), context_alias="risk_manager")


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Main entry point for BiRRe MCP server."""

    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        _run_server(_CliOptions())
        return

    if args[0] in {"-h", "--help"}:
        app.main(args=args, prog_name=_PROG_NAME)
        return

    if args[0].startswith("-"):
        app.main(args=["serve", *args], prog_name=_PROG_NAME)
    else:
        app.main(args=args, prog_name=_PROG_NAME)


if __name__ == "__main__":
    main()
