"""Typer registration for the BiRRe ``run`` command."""

from __future__ import annotations

import cProfile
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer

from birre.cli import options as cli_options
from birre.cli.invocation import build_invocation, resolve_runtime_and_logging
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
            api_key=bitsight_api_key,
            subscription_folder=subscription_folder,
            subscription_type=subscription_type,
            context=context,
            context_choices=CONTEXT_CHOICES,
            debug=debug,
            risk_vector_filter=risk_vector_filter,
            max_findings=max_findings,
            skip_startup_checks=skip_startup_checks,
            allow_insecure_tls=allow_insecure_tls,
            ca_bundle=ca_bundle,
            log_level=log_level,
            log_format=log_format,
            log_file=log_file,
            log_max_bytes=log_max_bytes,
            log_backup_count=log_backup_count,
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

        try:
            online_result = run_online_checks(runtime_settings, logger=logger)
            if inspect.isawaitable(online_result):
                online_ok = await_sync(online_result)
            else:
                online_ok = online_result
        except BirreError as exc:
            logger.critical(
                "Online startup checks failed; aborting startup",
                **exc.log_fields(),
            )
            raise typer.Exit(code=1) from exc

        if not online_ok:
            logger.critical("Online startup checks failed; aborting startup")
            raise typer.Exit(code=1)

        server = prepare_server(runtime_settings, logger)

        logger.info("Starting BiRRe FastMCP server")
        try:
            if invocation.profile_path is not None:
                invocation.profile_path.parent.mkdir(parents=True, exist_ok=True)
                profiler = cProfile.Profile()
                profiler.enable()
                try:
                    server.run()
                finally:
                    profiler.disable()
                    profiler.dump_stats(str(invocation.profile_path))
                    logger.info("Profiling data written", profile=str(invocation.profile_path))
            else:
                server.run()
        except KeyboardInterrupt:
            stderr_console.print(keyboard_interrupt_banner())
            logger.info("BiRRe stopped via KeyboardInterrupt")


__all__ = ["register"]
