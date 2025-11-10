"""Typer registration for the BiRRe ``run`` command."""

from __future__ import annotations

import cProfile
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer

from birre.cli import options as cli_options
from birre.cli.invocation import (
    AuthCliInputs,
    LoggingCliInputs,
    RuntimeCliInputs,
    SubscriptionCliInputs,
    TlsCliInputs,
    build_invocation,
    resolve_runtime_and_logging,
)
from birre.cli.runtime import (
    CONTEXT_CHOICES,
    initialize_logging,
    prepare_server,
    run_offline_checks,
    run_online_checks,
)
from birre.cli.sync_bridge import await_sync
from birre.config.constants import DEFAULT_CONFIG_FILENAME
from birre.infrastructure.errors import BirreError


def register(
    app: typer.Typer,
    *,
    stderr_console: Any,
    banner_factory: Callable[[], object],
    keyboard_interrupt_banner: Callable[[], object],
) -> None:
    """Register the ``run`` command on the provided Typer app."""

    @app.command(
        help="Start the BiRRe FastMCP server with BitSight connectivity.",
    )
    def run(  # NOSONAR python:S107
        config: cli_options.ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),  # NOSONAR
        bitsight_api_key: cli_options.BitsightApiKeyOption = None,
        subscription_folder: cli_options.SubscriptionFolderOption = None,
        subscription_type: cli_options.SubscriptionTypeOption = None,
        skip_startup_checks: cli_options.SkipStartupChecksOption = None,
        debug: cli_options.DebugOption = None,
        allow_insecure_tls: cli_options.AllowInsecureTlsOption = None,
        ca_bundle: cli_options.CaBundleOption = None,
        context: cli_options.ContextOption = None,
        risk_vector_filter: cli_options.RiskVectorFilterOption = None,
        max_findings: cli_options.MaxFindingsOption = None,
        log_level: cli_options.LogLevelOption = None,
        log_format: cli_options.LogFormatOption = None,
        log_file: cli_options.LogFileOption = None,
        log_max_bytes: cli_options.LogMaxBytesOption = None,
        log_backup_count: cli_options.LogBackupCountOption = None,
        profile: cli_options.ProfilePathOption = None,
    ) -> None:
        """Start the BiRRe FastMCP server with the configured runtime options."""

        invocation = build_invocation(
            config_path=str(config) if config is not None else None,
            context_choices=CONTEXT_CHOICES,
            auth=AuthCliInputs(api_key=bitsight_api_key),
            subscription=SubscriptionCliInputs(
                folder=subscription_folder,
                type=subscription_type,
            ),
            runtime=RuntimeCliInputs(
                context=context,
                debug=debug,
                risk_vector_filter=risk_vector_filter,
                max_findings=max_findings,
                skip_startup_checks=skip_startup_checks,
            ),
            tls=TlsCliInputs(
                allow_insecure_tls=allow_insecure_tls,
                ca_bundle=ca_bundle,
            ),
            logging=LoggingCliInputs(
                level=log_level,
                format=log_format,
                file_path=log_file,
                max_bytes=log_max_bytes,
                backup_count=log_backup_count,
            ),
            profile_path=profile,
        )

        runtime_settings, logging_settings, _ = resolve_runtime_and_logging(invocation)
        logger = initialize_logging(
            runtime_settings,
            logging_settings,
            show_banner=True,
            banner_printer=lambda: stderr_console.print(banner_factory()),
        )

        if not run_offline_checks(runtime_settings, logger=logger):
            raise typer.Exit(code=1)

        online_ok = _execute_online_checks(runtime_settings, logger)
        if not online_ok:
            logger.critical("Online startup checks failed; aborting startup")
            raise typer.Exit(code=1)

        server = prepare_server(runtime_settings, logger)
        _run_server_with_optional_profile(
            server,
            invocation,
            logger,
            stderr_console,
            keyboard_interrupt_banner,
        )


__all__ = ["register"]


def _execute_online_checks(runtime_settings: Any, logger: Any) -> bool:
    try:
        online_result = run_online_checks(runtime_settings, logger=logger)
    except BirreError as exc:
        logger.critical(
            "Online startup checks failed; aborting startup",
            **exc.log_fields(),
        )
        raise typer.Exit(code=1) from exc

    if inspect.isawaitable(online_result):
        return await_sync(online_result)
    return bool(online_result)


def _run_server_with_optional_profile(
    server: Any,
    invocation: Any,
    logger: Any,
    stderr_console: Any,
    keyboard_interrupt_banner: Callable[[], object],
) -> None:
    logger.info("Starting BiRRe FastMCP server")
    try:
        if invocation.profile_path is not None:
            _run_profiled_server(server, invocation.profile_path, logger)
        else:
            server.run()
    except KeyboardInterrupt:
        stderr_console.print(keyboard_interrupt_banner())
        logger.info("BiRRe stopped via KeyboardInterrupt")


def _run_profiled_server(server: Any, profile_path: Path, logger: Any) -> None:
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profiler = cProfile.Profile()
    profiler.enable()
    try:
        server.run()
    finally:
        profiler.disable()
        profiler.dump_stats(str(profile_path))
        logger.info("Profiling data written", profile=str(profile_path))
