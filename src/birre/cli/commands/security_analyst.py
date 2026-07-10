"""CLI adapter for the security-analyst alert workflow."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import typer

from birre.application.server import create_birre_server
from birre.cli import options as cli_options
from birre.cli.invocation import (
    AuthCliInputs,
    TlsCliInputs,
    build_invocation,
    resolve_runtime_and_logging,
)
from birre.cli.sync_bridge import await_sync
from birre.config.constants import DEFAULT_CONFIG_FILENAME
from birre.domain.security_analyst.workflow import run_alert_workflow_action_payload
from birre.infrastructure.logging import get_logger


class _CliWorkflowContext:
    def __init__(self, logger: Any) -> None:
        self._logger = logger

    async def info(self, message: str) -> None:
        self._logger.info(message)

    async def warning(self, message: str) -> None:
        self._logger.warning(message)

    async def error(self, message: str) -> None:
        self._logger.error(message)


def register(
    app: typer.Typer,
    *,
    workflow_runner: Callable[..., Any] | None = None,
) -> None:
    """Register the JSON workflow command with an injectable runner."""
    runner = workflow_runner or run_alert_workflow_action_payload

    @app.command("security-analyst-alerts", help="Prepare JSON Jira actions from BitSight alerts.")
    def security_analyst_alerts(
        config: Path = typer.Option(Path(DEFAULT_CONFIG_FILENAME)),
        bitsight_api_key: cli_options.BitsightApiKeyOption = None,
        allow_insecure_tls: cli_options.AllowInsecureTlsOption = None,
        ca_bundle: cli_options.CaBundleOption = None,
        alert_date_gte: str | None = typer.Option(
            None, help="Only include alerts on or after this date."
        ),
        page_size: int = typer.Option(50),
        max_pages: int = typer.Option(10),
        max_companies: int = typer.Option(100),
        max_returned_priority: int = typer.Option(4),
    ) -> None:
        for name, value in (
            ("page_size", page_size),
            ("max_pages", max_pages),
            ("max_companies", max_companies),
        ):
            if value <= 0:
                raise typer.BadParameter(
                    f"{name} must be greater than zero", param_hint=name
                )
        if max_returned_priority < 0:
            raise typer.BadParameter(
                "max_returned_priority must not be negative",
                param_hint="max_returned_priority",
            )
        workflow_options = {
            "alert_date_gte": alert_date_gte,
            "page_size": page_size,
            "max_pages": max_pages,
            "max_companies": max_companies,
            "max_returned_priority": max_returned_priority,
        }
        if workflow_runner is not None:
            result = runner(**workflow_options)
        else:
            result = _run_production_workflow(
                config=config,
                bitsight_api_key=bitsight_api_key,
                allow_insecure_tls=allow_insecure_tls,
                ca_bundle=ca_bundle,
                workflow_options=workflow_options,
            )
        if inspect.isawaitable(result):
            result = await_sync(result)
        if not isinstance(result, Mapping):
            raise typer.BadParameter("workflow runner must return a mapping")
        typer.echo(json.dumps(result, default=str))


def _run_production_workflow(
    *,
    config: Path,
    bitsight_api_key: str | None,
    allow_insecure_tls: bool | None,
    ca_bundle: str | None,
    workflow_options: Mapping[str, Any],
) -> Any:
    invocation = build_invocation(
        config_path=config,
        context_choices=frozenset({"security_analyst"}),
        auth=AuthCliInputs(api_key=bitsight_api_key),
        tls=TlsCliInputs(
            allow_insecure_tls=allow_insecure_tls,
            ca_bundle=ca_bundle,
        ),
    )
    runtime_settings, _, _ = resolve_runtime_and_logging(invocation)
    runtime_settings = replace(runtime_settings, context="security_analyst")
    logger = get_logger("birre")
    server = create_birre_server(runtime_settings, logger)
    call_v2_tool = getattr(server, "call_v2_tool", None)
    call_v1_tool = getattr(server, "call_v1_tool", None)
    if call_v2_tool is None or call_v1_tool is None:
        raise typer.BadParameter("security analyst API clients are not configured")
    ctx = _CliWorkflowContext(logger)

    async def fetch_company(company_guid: str) -> Any:
        return await call_v1_tool("getCompany", ctx, {"guid": company_guid})

    return run_alert_workflow_action_payload(
        call_v2_tool,
        fetch_company,
        ctx,
        **workflow_options,
    )


__all__ = ["register"]