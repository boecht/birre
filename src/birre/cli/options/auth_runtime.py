"""Authentication and runtime option definitions.

Provides Typer option declarations for API authentication, runtime behavior,
subscription management, and TLS configuration.
"""

from __future__ import annotations

from typing import Annotated

import typer

BitsightApiKeyOption = Annotated[
    str | None,
    typer.Option(
        "--bitsight-api-key",
        help="BitSight API key (overrides BITSIGHT_API_KEY env var)",
        envvar="BITSIGHT_API_KEY",
        show_envvar=True,
        rich_help_panel="Authentication",
    ),
]

SubscriptionFolderOption = Annotated[
    str | None,
    typer.Option(
        "--subscription-folder",
        help="BitSight subscription folder override",
        envvar="BIRRE_SUBSCRIPTION_FOLDER",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

SubscriptionTypeOption = Annotated[
    str | None,
    typer.Option(
        "--subscription-type",
        help="BitSight subscription type override",
        envvar="BIRRE_SUBSCRIPTION_TYPE",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

ContextOption = Annotated[
    str | None,
    typer.Option(
        "--context",
        help="Tool persona to expose (standard or risk_manager)",
        envvar="BIRRE_CONTEXT",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

RiskVectorFilterOption = Annotated[
    str | None,
    typer.Option(
        "--risk-vector-filter",
        help="Comma separated list of BitSight risk vectors",
        envvar="BIRRE_RISK_VECTOR_FILTER",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

MaxFindingsOption = Annotated[
    int | None,
    typer.Option(
        "--max-findings",
        min=1,
        help="Maximum number of findings to surface per company",
        envvar="BIRRE_MAX_FINDINGS",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

SkipStartupChecksOption = Annotated[
    bool | None,
    typer.Option(
        "--skip-startup-checks/--require-startup-checks",
        help=(
            "Skip online startup checks "
            "(use --require-startup-checks to override any configured skip)"
        ),
        envvar="BIRRE_SKIP_STARTUP_CHECKS",
        show_envvar=True,
        rich_help_panel="Runtime",
    ),
]

DebugOption = Annotated[
    bool | None,
    typer.Option(
        "--debug/--no-debug",
        help="Enable verbose diagnostics",
        envvar="BIRRE_DEBUG",
        show_envvar=True,
        rich_help_panel="Diagnostics",
    ),
]

AllowInsecureTlsOption = Annotated[
    bool | None,
    typer.Option(
        "--allow-insecure-tls/--enforce-tls",
        help="Disable TLS verification for API calls (not recommended)",
        envvar="BIRRE_ALLOW_INSECURE_TLS",
        show_envvar=True,
        rich_help_panel="TLS",
    ),
]

CaBundleOption = Annotated[
    str | None,
    typer.Option(
        "--ca-bundle",
        help="Path to a custom certificate authority bundle, e.g. for TLS interception",
        envvar="BIRRE_CA_BUNDLE",
        show_envvar=True,
        rich_help_panel="TLS",
    ),
]

__all__ = [
    "AllowInsecureTlsOption",
    "BitsightApiKeyOption",
    "CaBundleOption",
    "ContextOption",
    "DebugOption",
    "MaxFindingsOption",
    "RiskVectorFilterOption",
    "SkipStartupChecksOption",
    "SubscriptionFolderOption",
    "SubscriptionTypeOption",
]
