"""Selftest command for BiRRe CLI."""

from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from birre.cli import options as cli_options
from birre.cli.commands.selftest.runner import SelfTestRunner
from birre.cli.invocation import (
    AuthCliInputs,
    LoggingCliInputs,
    RuntimeCliInputs,
    SubscriptionCliInputs,
    TlsCliInputs,
    build_invocation,
    resolve_runtime_and_logging,
)
from birre.cli.runtime import CONTEXT_CHOICES, initialize_logging
from birre.cli.sync_bridge import await_sync
from birre.config.constants import DEFAULT_CONFIG_FILENAME
from birre.infrastructure.errors import ErrorCode
from birre.infrastructure.logging import BoundLogger


def register(
    app: typer.Typer,
    *,
    stderr_console: Console,
    stdout_console: Console,
    banner_factory: Any,
    expected_tools_by_context: dict[str, Any],
    healthcheck_testing_v1_base_url: str,
    healthcheck_production_v1_base_url: str,
) -> None:
    """Register the selftest command with the given Typer app."""

    @app.command(help="Run BiRRe self tests without starting the FastMCP server.")
    def selftest(  # NOSONAR python:S107
        config: cli_options.ConfigPathOption = Path(DEFAULT_CONFIG_FILENAME),  # NOSONAR
        bitsight_api_key: cli_options.BitsightApiKeyOption = None,
        subscription_folder: cli_options.SubscriptionFolderOption = None,
        subscription_type: cli_options.SubscriptionTypeOption = None,
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
        offline: cli_options.OfflineFlagOption = False,
        production: cli_options.ProductionFlagOption = False,
    ) -> None:
        """Execute BiRRe diagnostics and optional online checks."""

        auth_inputs = AuthCliInputs(api_key=bitsight_api_key)
        subscription_inputs = SubscriptionCliInputs(
            folder=subscription_folder,
            type=subscription_type,
        )
        runtime_inputs = RuntimeCliInputs(
            context=None,
            debug=debug,
            risk_vector_filter=risk_vector_filter,
            max_findings=max_findings,
            skip_startup_checks=bool(offline),
        )
        tls_inputs = TlsCliInputs(
            allow_insecure_tls=allow_insecure_tls,
            ca_bundle=ca_bundle,
        )
        logging_inputs = LoggingCliInputs(
            level=log_level,
            format=log_format,
            file_path=log_file,
            max_bytes=log_max_bytes,
            backup_count=log_backup_count,
        )

        invocation = _build_selftest_invocation(
            config=config,
            auth_inputs=auth_inputs,
            subscription_inputs=subscription_inputs,
            runtime_inputs=runtime_inputs,
            tls_inputs=tls_inputs,
            logging_inputs=logging_inputs,
        )

        runtime_settings, logging_settings, _ = resolve_runtime_and_logging(invocation)
        logger = initialize_logging(
            runtime_settings,
            logging_settings,
            show_banner=False,
            banner_printer=lambda: stderr_console.print(banner_factory()),
        )

        target_base_url, environment_label = _resolve_selftest_environment(
            production,
            healthcheck_testing_v1_base_url,
            healthcheck_production_v1_base_url,
        )
        _log_environment_notice(
            logger,
            stdout_console,
            environment_label,
            target_base_url,
            offline,
        )

        runner = SelfTestRunner(
            runtime_settings=runtime_settings,
            logger=logger,
            offline=bool(offline),
            target_base_url=target_base_url,
            environment_label=environment_label,
            run_sync=await_sync,
            expected_tools_by_context=expected_tools_by_context,
        )
        result = runner.run()

        if ErrorCode.TLS_CERT_CHAIN_INTERCEPTED.value in result.alerts:
            stderr_console.print("[red]TLS interception detected.[/red]")
            stderr_console.print("Set BIRRE_CA_BUNDLE or use --allow-insecure-tls")

        # Import rendering function from rendering module
        from birre.cli.commands.selftest.rendering import render_healthcheck_summary

        render_healthcheck_summary(result.summary, stdout_console)

        _handle_selftest_exit(result, logger, environment_label)


def _build_selftest_invocation(
    *,
    config: Path,
    auth_inputs: AuthCliInputs,
    subscription_inputs: SubscriptionCliInputs,
    runtime_inputs: RuntimeCliInputs,
    tls_inputs: TlsCliInputs,
    logging_inputs: LoggingCliInputs,
) -> Any:
    return build_invocation(
        context_choices=CONTEXT_CHOICES,
        config_path=str(config) if config is not None else None,
        auth=auth_inputs,
        subscription=subscription_inputs,
        runtime=runtime_inputs,
        tls=tls_inputs,
        logging=logging_inputs,
    )


def _resolve_selftest_environment(
    production: bool,
    testing_base_url: str,
    production_base_url: str,
) -> tuple[str, str]:
    if production:
        return production_base_url, "production"
    return testing_base_url, "testing"


def _log_environment_notice(
    logger: BoundLogger,
    stdout_console: Console,
    environment_label: str,
    target_base_url: str,
    offline: bool,
) -> None:
    logger.info(
        "Configured BitSight API environment",
        environment=environment_label,
        base_url=target_base_url,
    )
    if environment_label == "testing" and not offline:
        stdout_console.print(
            "[yellow]Note:[/yellow] BitSight's testing environment often returns "
            "[bold]HTTP 403[/bold] for subscription management tools even with "
            "valid credentials. "
            "This is expected for accounts without sandbox write access. "
            "Re-run with [green]--production[/green] to validate against the live API."
        )
    if offline:
        logger.info("Offline mode enabled; skipping online diagnostics")


def _handle_selftest_exit(
    result: Any,
    logger: BoundLogger,
    environment_label: str,
) -> None:
    exit_code = result.exit_code()
    contexts = list(result.contexts)
    if exit_code == 1:
        logger.critical(
            "Health checks failed", contexts=contexts, environment=environment_label
        )
        raise typer.Exit(code=1)
    if exit_code == 2:
        logger.warning(
            "Health checks completed with warnings",
            contexts=contexts,
            environment=environment_label,
        )
        raise typer.Exit(code=2)

    logger.info(
        "Health checks completed successfully",
        contexts=contexts,
        environment=environment_label,
    )
