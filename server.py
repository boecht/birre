"""BiRRe FastMCP server entrypoint."""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional, Sequence

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
DebugOption = Annotated[
    Optional[bool],
    typer.Option(
        "--debug",
        help="Enable verbose debug logging and diagnostic payloads",
        envvar="BIRRE_DEBUG",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]


@dataclass(frozen=True)
class _AuthCliOverrides:
    api_key: Optional[str] = None


@dataclass(frozen=True)
class _LoggingCliOverrides:
    level: Optional[str] = None
    format: Optional[str] = None


@dataclass(frozen=True)
class _RuntimeCliOverrides:
    context: Optional[str] = None
    debug: Optional[bool] = None


@dataclass(frozen=True)
class _CliInvocation:
    config_path: str
    auth: _AuthCliOverrides
    runtime: _RuntimeCliOverrides
    logging: _LoggingCliOverrides
    context_alias: Optional[str] = None


def _build_invocation(
    *,
    config_path: str,
    api_key: Optional[str],
    runtime_context: Optional[str],
    debug: Optional[bool],
    log_level: Optional[str],
    log_format: Optional[str],
    context_alias: Optional[str],
) -> _CliInvocation:
    return _CliInvocation(
        config_path=config_path,
        auth=_AuthCliOverrides(api_key=api_key),
        runtime=_RuntimeCliOverrides(context=runtime_context, debug=debug),
        logging=_LoggingCliOverrides(level=log_level, format=log_format),
        context_alias=context_alias,
    )


def _invoke_server(invocation: _CliInvocation) -> None:
    alias_context = (
        _normalize_context(invocation.context_alias)
        if invocation.context_alias
        else None
    )
    requested_context = _normalize_context(invocation.runtime.context)
    if alias_context and requested_context and alias_context != requested_context:
        raise typer.BadParameter(
            f"Context '{requested_context}' conflicts with the '{alias_context}' command.",
            param_hint="--context",
        )
    normalized_context = alias_context or requested_context

    normalized_log_format = _normalize_log_format(invocation.logging.format)
    normalized_log_level = _normalize_log_level(invocation.logging.level)

    logging_inputs = LoggingInputs(
        level=normalized_log_level,
        format=normalized_log_format,
        file_path=None,
        max_bytes=None,
        backup_count=None,
    )
    runtime_inputs = RuntimeInputs(
        context=normalized_context,
        debug=invocation.runtime.debug,
        risk_vector_filter=None,
        max_findings=None,
        skip_startup_checks=None,
    )

    config_settings = load_settings(invocation.config_path)
    apply_cli_overrides(
        config_settings,
        api_key_input=invocation.auth.api_key,
        subscription_inputs=SubscriptionInputs(),
        runtime_inputs=runtime_inputs,
        tls_inputs=TlsInputs(),
        logging_inputs=logging_inputs,
    )

    runtime_settings = runtime_from_settings(config_settings)
    logging_settings = logging_from_settings(config_settings)
    if runtime_settings.debug and logging_settings.level > logging.DEBUG:
        logging_settings = replace(logging_settings, level=logging.DEBUG)

    console.print(_banner(), markup=False)

    configure_logging(logging_settings)
    logger = get_logger("birre")

    for message in runtime_settings.overrides:
        logger.info(message)

    for message in runtime_settings.warnings:
        logger.warning(message)

    logger.info("Running offline startup checks")
    offline_ok = run_offline_startup_checks(
        has_api_key=bool(runtime_settings.api_key),  # CodeQL false positive
        subscription_folder=runtime_settings.subscription_folder,
        subscription_type=runtime_settings.subscription_type,
        logger=logger,
    )
    if not offline_ok:
        logger.critical("Offline startup checks failed; aborting startup")
        raise SystemExit(1)

    logger.info("Preparing BiRRe FastMCP server")
    server = create_birre_server(settings=runtime_settings, logger=logger)

    logger.info("Running online startup checks")
    call_v1_tool = getattr(server, "call_v1_tool", None)
    online_ok = asyncio.run(
        run_online_startup_checks(
            call_v1_tool=call_v1_tool,
            subscription_folder=runtime_settings.subscription_folder,
            subscription_type=runtime_settings.subscription_type,
            logger=logger,
            skip_startup_checks=runtime_settings.skip_startup_checks,
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


def _execute_command(
    *,
    context_alias: Optional[str],
    config_path: str,
    api_key: Optional[str],
    runtime_context: Optional[str],
    debug: Optional[bool],
    log_level: Optional[str],
    log_format: Optional[str],
) -> None:
    invocation = _build_invocation(
        config_path=config_path,
        api_key=api_key,
        runtime_context=runtime_context,
        debug=debug,
        log_level=log_level,
        log_format=log_format,
        context_alias=context_alias,
    )
    _invoke_server(invocation)


@app.command(help="Serve BiRRe with an explicitly selected context.")
def serve(
    config_path: ConfigPathOption = DEFAULT_CONFIG_FILENAME,
    context: ContextOption = None,
    api_key: ApiKeyOption = None,
    log_level: LogLevelOption = None,
    log_format: LogFormatOption = None,
    debug: DebugOption = None,
) -> None:
    """Run BiRRe with optional context overrides from the CLI."""

    _execute_command(
        context_alias=None,
        config_path=config_path,
        api_key=api_key,
        runtime_context=context,
        debug=debug,
        log_level=log_level,
        log_format=log_format,
    )


@app.command(help="Serve BiRRe using the standard tool persona.")
def standard(
    config_path: ConfigPathOption = DEFAULT_CONFIG_FILENAME,
    api_key: ApiKeyOption = None,
    log_level: LogLevelOption = None,
    log_format: LogFormatOption = None,
    debug: DebugOption = None,
) -> None:
    """Run BiRRe locked to the standard context."""

    _execute_command(
        context_alias="standard",
        config_path=config_path,
        api_key=api_key,
        runtime_context=None,
        debug=debug,
        log_level=log_level,
        log_format=log_format,
    )


@app.command("risk-manager", help="Serve BiRRe using the risk manager persona.")
def risk_manager(
    config_path: ConfigPathOption = DEFAULT_CONFIG_FILENAME,
    api_key: ApiKeyOption = None,
    log_level: LogLevelOption = None,
    log_format: LogFormatOption = None,
    debug: DebugOption = None,
) -> None:
    """Run BiRRe locked to the risk manager context."""

    _execute_command(
        context_alias="risk_manager",
        config_path=config_path,
        api_key=api_key,
        runtime_context=None,
        debug=debug,
        log_level=log_level,
        log_format=log_format,
    )


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Main entry point for BiRRe MCP server."""

    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        _invoke_server(
            _build_invocation(
                config_path=DEFAULT_CONFIG_FILENAME,
                api_key=None,
                runtime_context=None,
                debug=None,
                log_level=None,
                log_format=None,
                context_alias=None,
            )
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
