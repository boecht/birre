"""Data models used by the BiRRe CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuthOverrides:
    """Authentication-related CLI overrides."""

    api_key: str | None = None


@dataclass(frozen=True)
class SubscriptionOverrides:
    """Subscription-related CLI overrides."""

    folder: str | None = None
    type: str | None = None


@dataclass(frozen=True)
class RuntimeOverrides:
    """Runtime behaviour overrides."""

    context: str | None = None
    debug: bool | None = None
    risk_vector_filter: str | None = None
    max_findings: int | None = None
    skip_startup_checks: bool | None = None


@dataclass(frozen=True)
class TlsOverrides:
    """TLS verification overrides."""

    allow_insecure: bool | None = None
    ca_bundle_path: str | None = None


@dataclass(frozen=True)
class LoggingOverrides:
    """Logging-related CLI overrides."""

    level: str | None = None
    format: str | None = None
    file_path: str | None = None
    max_bytes: int | None = None
    backup_count: int | None = None


@dataclass
class LogViewLine:
    """Parsed representation of a log line for display/filters."""

    raw: str
    level: int | None
    timestamp: float | None
    json_data: dict[str, Any | None] | None = None


@dataclass(frozen=True)
class CliInvocation:
    """Resolved CLI invocation context."""

    config_path: str | None
    auth: AuthOverrides
    subscription: SubscriptionOverrides
    runtime: RuntimeOverrides
    tls: TlsOverrides
    logging: LoggingOverrides
    profile_path: Path | None = None


__all__ = [
    "AuthOverrides",
    "CliInvocation",
    "LogViewLine",
    "LoggingOverrides",
    "RuntimeOverrides",
    "SubscriptionOverrides",
    "TlsOverrides",
]
