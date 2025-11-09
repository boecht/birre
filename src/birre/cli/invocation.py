"""CLI invocation building and settings conversion.

Handles construction of CLI invocations from command-line parameters
and conversion between CLI overrides and settings input objects.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from birre.cli.models import (
    AuthOverrides,
    CliInvocation,
    LoggingOverrides,
    RuntimeOverrides,
    SubscriptionOverrides,
    TlsOverrides,
)
from birre.cli.options import core as cli_options
from birre.config.settings import (
    LoggingInputs,
    RuntimeInputs,
    SubscriptionInputs,
    TlsInputs,
    apply_cli_overrides,
    is_logfile_disabled_value,
    load_settings,
    logging_from_settings,
    runtime_from_settings,
)


@dataclass(frozen=True)
class AuthCliInputs:
    api_key: str | None = None


@dataclass(frozen=True)
class SubscriptionCliInputs:
    folder: str | None = None
    type: str | None = None


@dataclass(frozen=True)
class RuntimeCliInputs:
    context: str | None = None
    debug: bool | None = None
    risk_vector_filter: str | None = None
    max_findings: int | None = None
    skip_startup_checks: bool | None = None


@dataclass(frozen=True)
class TlsCliInputs:
    allow_insecure_tls: bool | None = None
    ca_bundle: str | None = None


@dataclass(frozen=True)
class LoggingCliInputs:
    level: str | None = None
    format: str | None = None
    file_path: str | None = None
    max_bytes: int | None = None
    backup_count: int | None = None


def build_invocation(
    *,
    config_path: Path | str | None,
    context_choices: frozenset[str],
    auth: AuthCliInputs | None = None,
    subscription: SubscriptionCliInputs | None = None,
    runtime: RuntimeCliInputs | None = None,
    tls: TlsCliInputs | None = None,
    logging: LoggingCliInputs | None = None,
    profile_path: Path | None = None,
) -> CliInvocation:
    """Construct a :class:`CliInvocation` with normalized CLI parameters."""

    auth_inputs = auth or AuthCliInputs()
    subscription_inputs = subscription or SubscriptionCliInputs()
    runtime_inputs = runtime or RuntimeCliInputs()
    tls_inputs = tls or TlsCliInputs()
    logging_inputs = logging or LoggingCliInputs()

    normalized_context = cli_options.normalize_context(
        runtime_inputs.context, choices=context_choices
    )
    normalized_log_format = cli_options.normalize_log_format(logging_inputs.format)
    normalized_log_level = cli_options.normalize_log_level(logging_inputs.level)
    normalized_max_findings = cli_options.validate_positive(
        "max_findings", runtime_inputs.max_findings
    )
    normalized_log_max_bytes = cli_options.validate_positive(
        "log_max_bytes", logging_inputs.max_bytes
    )
    normalized_log_backup_count = cli_options.validate_positive(
        "log_backup_count", logging_inputs.backup_count
    )

    clean_log_file = cli_options.clean_string(logging_inputs.file_path)

    return CliInvocation(
        config_path=str(config_path) if config_path is not None else None,
        auth=AuthOverrides(api_key=cli_options.clean_string(auth_inputs.api_key)),
        subscription=SubscriptionOverrides(
            folder=cli_options.clean_string(subscription_inputs.folder),
            type=cli_options.clean_string(subscription_inputs.type),
        ),
        runtime=RuntimeOverrides(
            context=normalized_context,
            debug=runtime_inputs.debug,
            risk_vector_filter=cli_options.clean_string(
                runtime_inputs.risk_vector_filter
            ),
            max_findings=normalized_max_findings,
            skip_startup_checks=runtime_inputs.skip_startup_checks,
        ),
        tls=TlsOverrides(
            allow_insecure=tls_inputs.allow_insecure_tls,
            ca_bundle_path=cli_options.clean_string(tls_inputs.ca_bundle),
        ),
        logging=LoggingOverrides(
            level=normalized_log_level,
            format=normalized_log_format,
            file_path=clean_log_file,
            max_bytes=normalized_log_max_bytes,
            backup_count=normalized_log_backup_count,
        ),
        profile_path=profile_path,
    )


def subscription_inputs(overrides: SubscriptionOverrides) -> SubscriptionInputs | None:
    """Convert CLI subscription overrides to :class:`SubscriptionInputs`."""

    if overrides.folder is None and overrides.type is None:
        return None
    return SubscriptionInputs(folder=overrides.folder, type=overrides.type)


def runtime_inputs(overrides: RuntimeOverrides) -> RuntimeInputs | None:
    """Convert CLI runtime overrides to :class:`RuntimeInputs`."""

    if (
        overrides.context is None
        and overrides.debug is None
        and overrides.risk_vector_filter is None
        and overrides.max_findings is None
        and overrides.skip_startup_checks is None
    ):
        return None
    return RuntimeInputs(
        context=overrides.context,
        debug=overrides.debug,
        risk_vector_filter=overrides.risk_vector_filter,
        max_findings=overrides.max_findings,
        skip_startup_checks=overrides.skip_startup_checks,
    )


def tls_inputs(overrides: TlsOverrides) -> TlsInputs | None:
    """Convert CLI TLS overrides to :class:`TlsInputs`."""

    if overrides.allow_insecure is None and overrides.ca_bundle_path is None:
        return None
    return TlsInputs(
        allow_insecure=overrides.allow_insecure,
        ca_bundle_path=overrides.ca_bundle_path,
    )


def logging_inputs(overrides: LoggingOverrides) -> LoggingInputs | None:
    """Convert CLI logging overrides to :class:`LoggingInputs`."""

    if (
        overrides.level is None
        and overrides.format is None
        and overrides.file_path is None
        and overrides.max_bytes is None
        and overrides.backup_count is None
    ):
        return None

    file_override: str | None
    if overrides.file_path is None:
        file_override = None
    elif is_logfile_disabled_value(overrides.file_path):
        file_override = ""
    else:
        file_override = overrides.file_path

    return LoggingInputs(
        level=overrides.level,
        format=overrides.format,
        file_path=file_override,
        max_bytes=overrides.max_bytes,
        backup_count=overrides.backup_count,
    )


def load_settings_from_invocation(
    invocation: CliInvocation,
) -> Any:  # Returns BirreSettings
    """Load settings and apply CLI overrides."""

    settings = load_settings(invocation.config_path)
    apply_cli_overrides(
        settings,
        api_key_input=invocation.auth.api_key,
        subscription_inputs=subscription_inputs(invocation.subscription),
        runtime_inputs=runtime_inputs(invocation.runtime),
        tls_inputs=tls_inputs(invocation.tls),
        logging_inputs=logging_inputs(invocation.logging),
    )
    return settings


def resolve_runtime_and_logging(
    invocation: CliInvocation,
) -> tuple[Any, Any, Any]:  # (RuntimeSettings, LoggingSettings, Settings)
    """Resolve runtime and logging settings from a CLI invocation."""

    import logging

    settings = load_settings_from_invocation(invocation)
    runtime_settings = runtime_from_settings(settings)
    logging_settings = logging_from_settings(settings)
    if runtime_settings.debug and logging_settings.level > logging.DEBUG:
        logging_settings = replace(logging_settings, level=logging.DEBUG)
    return runtime_settings, logging_settings, settings


__all__ = [
    "AuthCliInputs",
    "build_invocation",
    "load_settings_from_invocation",
    "logging_inputs",
    "LoggingCliInputs",
    "resolve_runtime_and_logging",
    "RuntimeCliInputs",
    "runtime_inputs",
    "SubscriptionCliInputs",
    "subscription_inputs",
    "TlsCliInputs",
    "tls_inputs",
]
