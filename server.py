"""BiRRe FastMCP server entrypoint."""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, replace
from functools import wraps
from typing import Callable, Optional, Sequence, cast

import click
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

_CONTEXT_CHOICES = {"standard", "risk_manager"}
_LOG_FORMAT_CHOICES = {"text", "json"}
_LOG_LEVEL_CHOICES = sorted(
    name
    for name, value in logging.getLevelNamesMapping().items()
    if isinstance(name, str) and not name.isdigit()
)
_LOG_LEVEL_SET = {choice.upper() for choice in _LOG_LEVEL_CHOICES}
_PROG_NAME = "server.py"


@dataclass
class CliOverrides:
    """CLI supplied overrides for server runtime configuration."""

    api_key: Optional[str]
    config_path: str
    log_level: Optional[str]
    log_format: Optional[str]
    log_file: Optional[str]
    log_max_bytes: Optional[int]
    log_backup_count: Optional[int]
    skip_startup_checks: Optional[bool]
    subscription_folder: Optional[str]
    subscription_type: Optional[str]
    risk_vector_filter: Optional[str]
    max_findings: Optional[int]
    debug: Optional[bool]
    allow_insecure_tls: Optional[bool]
    ca_bundle_path: Optional[str]


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


def _with_common_cli_options(
    func: Callable[..., None],
) -> Callable[..., None]:
    """Attach shared CLI options and store them on the Typer context."""

    @wraps(func)
    def command_wrapper(ctx: typer.Context, *args: object, **kwargs: object) -> None:
        overrides = CliOverrides(
            api_key=cast(Optional[str], kwargs.pop("api_key")),
            config_path=cast(str, kwargs.pop("config_path")),
            log_level=cast(Optional[str], kwargs.pop("log_level")),
            log_format=cast(Optional[str], kwargs.pop("log_format")),
            log_file=cast(Optional[str], kwargs.pop("log_file")),
            log_max_bytes=cast(Optional[int], kwargs.pop("log_max_bytes")),
            log_backup_count=cast(Optional[int], kwargs.pop("log_backup_count")),
            skip_startup_checks=cast(Optional[bool], kwargs.pop("skip_startup_checks")),
            subscription_folder=cast(Optional[str], kwargs.pop("subscription_folder")),
            subscription_type=cast(Optional[str], kwargs.pop("subscription_type")),
            risk_vector_filter=cast(Optional[str], kwargs.pop("risk_vector_filter")),
            max_findings=cast(Optional[int], kwargs.pop("max_findings")),
            debug=cast(Optional[bool], kwargs.pop("debug")),
            allow_insecure_tls=cast(Optional[bool], kwargs.pop("allow_insecure_tls")),
            ca_bundle_path=cast(Optional[str], kwargs.pop("ca_bundle_path")),
        )
        ctx.obj = overrides
        return func(ctx, *args, **kwargs)

    command_wrapper = click.pass_context(command_wrapper)

    option_decorators = [
        click.option(
            "--bitsight-api-key",
            "api_key",
            default=None,
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
        click.option(
            "--log-level",
            "log_level",
            default=None,
            help="Logging level (defaults to INFO unless overridden)",
            envvar="BIRRE_LOG_LEVEL",
            show_envvar=True,
        ),
        click.option(
            "--log-format",
            "log_format",
            default=None,
            help="Logging format (text or json)",
            envvar="BIRRE_LOG_FORMAT",
            show_envvar=True,
        ),
        click.option(
            "--log-file",
            "log_file",
            default=None,
            help="Log file path (adds rotating file handler)",
            envvar="BIRRE_LOG_FILE",
            show_envvar=True,
        ),
        click.option(
            "--log-max-bytes",
            "log_max_bytes",
            default=None,
            type=int,
            help="Maximum size in bytes for rotating log files",
            envvar="BIRRE_LOG_MAX_BYTES",
            show_envvar=True,
        ),
        click.option(
            "--log-backup-count",
            "log_backup_count",
            default=None,
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
            default=None,
            help="Preferred BitSight subscription folder name (e.g. API), must exist",
            envvar="BIRRE_SUBSCRIPTION_FOLDER",
            show_envvar=True,
        ),
        click.option(
            "--subscription-type",
            "subscription_type",
            default=None,
            help="BitSight subscription type (e.g. continuous_monitoring)",
            envvar="BIRRE_SUBSCRIPTION_TYPE",
            show_envvar=True,
        ),
        click.option(
            "--risk-vector-filter",
            "risk_vector_filter",
            default=None,
            help="Override the default risk vectors used for top findings (comma-separated).",
            envvar="BIRRE_RISK_VECTOR_FILTER",
            show_envvar=True,
        ),
        click.option(
            "--max-findings",
            "max_findings",
            default=None,
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
            default=None,
            help=(
                "Path to a custom CA bundle for BitSight API HTTPS verification "
                "(overrides system trust store)."
            ),
            envvar="BIRRE_CA_BUNDLE",
            show_envvar=True,
        ),
    ]

    for decorator in reversed(option_decorators):
        command_wrapper = decorator(command_wrapper)

    return command_wrapper


def _get_overrides(ctx: typer.Context) -> CliOverrides:
    """Retrieve CLI overrides stored on the Typer context."""

    return cast(CliOverrides, ctx.obj)


def _run_server(
    *,
    overrides: CliOverrides,
    context: Optional[str],
    context_alias: Optional[str] = None,
) -> None:
    alias_context = _normalize_context(context_alias) if context_alias else None
    requested_context = _normalize_context(context)
    if alias_context and requested_context and alias_context != requested_context:
        raise typer.BadParameter(
            f"Context '{requested_context}' conflicts with the '{alias_context}' command.",
            param_hint="--context",
        )
    normalized_context = alias_context or requested_context

    normalized_log_format = _normalize_log_format(overrides.log_format)
    normalized_log_level = _normalize_log_level(overrides.log_level)

    logging_inputs = LoggingInputs(
        level=normalized_log_level,
        format=normalized_log_format,
        file_path=overrides.log_file,
        max_bytes=overrides.log_max_bytes,
        backup_count=overrides.log_backup_count,
    )
    runtime_inputs = RuntimeInputs(
        context=normalized_context,
        debug=overrides.debug,
        risk_vector_filter=overrides.risk_vector_filter,
        max_findings=overrides.max_findings,
        skip_startup_checks=overrides.skip_startup_checks,
    )
    subscription_inputs = SubscriptionInputs(
        folder=overrides.subscription_folder,
        type=overrides.subscription_type,
    )
    tls_inputs = TlsInputs(
        allow_insecure=overrides.allow_insecure_tls,
        ca_bundle_path=overrides.ca_bundle_path,
    )

    config_settings = load_settings(overrides.config_path)
    apply_cli_overrides(
        config_settings,
        api_key_input=overrides.api_key,
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
        overrides.skip_startup_checks
        if overrides.skip_startup_checks is not None
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
@_with_common_cli_options
def serve(ctx: typer.Context, context: ContextOption = None) -> None:
    """Run the BiRRe FastMCP server."""

    _run_server(
        overrides=_get_overrides(ctx),
        context=context,
    )


@app.command(help="Serve BiRRe using the standard tool persona.")
@_with_common_cli_options
def standard(ctx: typer.Context) -> None:
    """Run the BiRRe FastMCP server in the standard context."""

    _run_server(
        overrides=_get_overrides(ctx),
        context=None,
        context_alias="standard",
    )


@app.command("risk-manager", help="Serve BiRRe using the risk manager persona.")
@_with_common_cli_options
def risk_manager(ctx: typer.Context) -> None:
    """Run the BiRRe FastMCP server in the risk manager context."""

    _run_server(
        overrides=_get_overrides(ctx),
        context=None,
        context_alias="risk_manager",
    )


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Main entry point for BiRRe MCP server."""

    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        _run_server(
            overrides=CliOverrides(
                api_key=None,
                config_path=DEFAULT_CONFIG_FILENAME,
                log_level=None,
                log_format=None,
                log_file=None,
                log_max_bytes=None,
                log_backup_count=None,
                skip_startup_checks=None,
                subscription_folder=None,
                subscription_type=None,
                risk_vector_filter=None,
                max_findings=None,
                debug=None,
                allow_insecure_tls=None,
                ca_bundle_path=None,
            ),
            context=None,
        )
        return

    command = get_command(app)
    if args[0] in {"-h", "--help"}:
        command.main(args=args, prog_name=_PROG_NAME)
        return

    if args[0].startswith("-"):
        command.main(args=["serve", *args], prog_name=_PROG_NAME)
    else:
        command.main(args=args, prog_name=_PROG_NAME)


if __name__ == "__main__":
    main()
