"""Dynaconf-backed configuration helpers for BiRRe."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from dynaconf import Dynaconf

from .constants import DEFAULT_CONFIG_FILENAME, LOCAL_CONFIG_FILENAME

_REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_RISK_VECTOR_FILTER = ",".join(
    [
        "botnet_infections",
        "spam_propagation",
        "malware_servers",
        "unsolicited_comm",
        "potentially_exploited",
        "open_ports",
        "patching_cadence",
        "insecure_systems",
        "server_software",
    ]
)
DEFAULT_MAX_FINDINGS = 10

LOG_FORMAT_TEXT = "text"
LOG_FORMAT_JSON = "json"
DEFAULT_LOG_FORMAT = LOG_FORMAT_TEXT
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MAX_BYTES = 10_000_000
DEFAULT_BACKUP_COUNT = 5

_ALLOWED_CONTEXTS = {"standard", "risk_manager"}
_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}

# Dynaconf keys used throughout the module. Using constants helps avoid
# duplication and keeps environment and configuration lookups consistent.
BITSIGHT_API_KEY_KEY = "bitsight.api_key"
BITSIGHT_SUBSCRIPTION_FOLDER_KEY = "bitsight.subscription_folder"
BITSIGHT_SUBSCRIPTION_TYPE_KEY = "bitsight.subscription_type"

ROLE_CONTEXT_KEY = "roles.context"
ROLE_RISK_VECTOR_FILTER_KEY = "roles.risk_vector_filter"
ROLE_MAX_FINDINGS_KEY = "roles.max_findings"

RUNTIME_SKIP_STARTUP_CHECKS_KEY = "runtime.skip_startup_checks"
RUNTIME_DEBUG_KEY = "runtime.debug"
RUNTIME_ALLOW_INSECURE_TLS_KEY = "runtime.allow_insecure_tls"
RUNTIME_CA_BUNDLE_PATH_KEY = "runtime.ca_bundle_path"

LOGGING_LEVEL_KEY = "logging.level"
LOGGING_FORMAT_KEY = "logging.format"
LOGGING_FILE_KEY = "logging.file"
LOGGING_MAX_BYTES_KEY = "logging.max_bytes"
LOGGING_BACKUP_COUNT_KEY = "logging.backup_count"

_ENVIRONMENT_MAP = {
    "BITSIGHT_API_KEY": BITSIGHT_API_KEY_KEY,
    "BIRRE_SUBSCRIPTION_FOLDER": BITSIGHT_SUBSCRIPTION_FOLDER_KEY,
    "BIRRE_SUBSCRIPTION_TYPE": BITSIGHT_SUBSCRIPTION_TYPE_KEY,
    "BIRRE_CONTEXT": ROLE_CONTEXT_KEY,
    "BIRRE_RISK_VECTOR_FILTER": ROLE_RISK_VECTOR_FILTER_KEY,
    "BIRRE_MAX_FINDINGS": ROLE_MAX_FINDINGS_KEY,
    "BIRRE_SKIP_STARTUP_CHECKS": RUNTIME_SKIP_STARTUP_CHECKS_KEY,
    "BIRRE_DEBUG": RUNTIME_DEBUG_KEY,
    "BIRRE_ALLOW_INSECURE_TLS": RUNTIME_ALLOW_INSECURE_TLS_KEY,
    "BIRRE_CA_BUNDLE": RUNTIME_CA_BUNDLE_PATH_KEY,
    "BIRRE_LOG_LEVEL": LOGGING_LEVEL_KEY,
    "BIRRE_LOG_FORMAT": LOGGING_FORMAT_KEY,
    "BIRRE_LOG_FILE": LOGGING_FILE_KEY,
    "BIRRE_LOG_MAX_BYTES": LOGGING_MAX_BYTES_KEY,
    "BIRRE_LOG_BACKUP_COUNT": LOGGING_BACKUP_COUNT_KEY,
}


@dataclass(frozen=True)
class SubscriptionInputs:
    folder: Optional[str] = None
    type: Optional[str] = None


@dataclass(frozen=True)
class RuntimeInputs:
    context: Optional[str] = None
    debug: Optional[bool] = None
    risk_vector_filter: Optional[str] = None
    max_findings: Optional[int] = None
    skip_startup_checks: Optional[bool] = None


@dataclass(frozen=True)
class TlsInputs:
    allow_insecure: Optional[bool] = None
    ca_bundle_path: Optional[str] = None


@dataclass(frozen=True)
class LoggingInputs:
    level: Optional[str] = None
    format: Optional[str] = None
    file_path: Optional[str] = None
    max_bytes: Optional[int] = None
    backup_count: Optional[int] = None

    def as_kwargs(self) -> Dict[str, Optional[Any]]:
        return {
            "level_override": self.level,
            "format_override": self.format,
            "file_override": self.file_path,
            "max_bytes_override": self.max_bytes,
            "backup_count_override": self.backup_count,
        }


@dataclass(frozen=True)
class LoggingSettings:
    level: int
    format: str
    file_path: Optional[str]
    max_bytes: int
    backup_count: int

    @property
    def level_name(self) -> str:
        return logging.getLevelName(self.level)


def _default_settings_files(config_path: Optional[str]) -> Tuple[Sequence[str], Optional[str]]:
    if config_path:
        config_file = Path(config_path)
        local_file = config_file.with_name(f"{config_file.stem}.local{config_file.suffix}")
        files: list[str] = []
        if config_file.exists():
            files.append(str(config_file))
        if local_file.exists():
            files.append(str(local_file))
        return files or [str(config_file)], None
    return [DEFAULT_CONFIG_FILENAME, LOCAL_CONFIG_FILENAME], str(_REPO_ROOT)


def _coerce_str(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    return str(value)


def _coerce_bool(value: Optional[Any]) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return None
        if normalized in _TRUTHY:
            return True
        if normalized in _FALSY:
            return False
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _coerce_int(value: Optional[Any]) -> Optional[int]:
    if value is None:
        return None
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    return coerced


def _apply_environment_overrides(settings: Dynaconf) -> None:
    for env_var, key in _ENVIRONMENT_MAP.items():
        raw = os.getenv(env_var)
        if raw is None:
            continue
        if isinstance(raw, str) and not raw.strip():
            continue
        settings.set(key, raw)
    debug_fallback = os.getenv("DEBUG")
    if debug_fallback and debug_fallback.strip():
        settings.set(RUNTIME_DEBUG_KEY, debug_fallback)


def _apply_api_key(settings: Dynaconf, api_key_input: Optional[str]) -> None:
    if api_key_input:
        settings.set(BITSIGHT_API_KEY_KEY, api_key_input)


def _apply_subscription_inputs(
    settings: Dynaconf, subscription_inputs: Optional[SubscriptionInputs]
) -> None:
    if subscription_inputs is None:
        return

    if subscription_inputs.folder is not None:
        settings.set(BITSIGHT_SUBSCRIPTION_FOLDER_KEY, subscription_inputs.folder.strip())
    if subscription_inputs.type is not None:
        settings.set(BITSIGHT_SUBSCRIPTION_TYPE_KEY, subscription_inputs.type.strip())


def _apply_runtime_inputs(
    settings: Dynaconf, runtime_inputs: Optional[RuntimeInputs]
) -> None:
    if runtime_inputs is None:
        return

    if runtime_inputs.context is not None:
        settings.set(ROLE_CONTEXT_KEY, runtime_inputs.context.strip())
    if runtime_inputs.debug is not None:
        settings.set(RUNTIME_DEBUG_KEY, runtime_inputs.debug)
    if runtime_inputs.risk_vector_filter is not None:
        settings.set(
            ROLE_RISK_VECTOR_FILTER_KEY, runtime_inputs.risk_vector_filter.strip()
        )
    if runtime_inputs.max_findings is not None:
        settings.set(ROLE_MAX_FINDINGS_KEY, runtime_inputs.max_findings)
    if runtime_inputs.skip_startup_checks is not None:
        settings.set(
            RUNTIME_SKIP_STARTUP_CHECKS_KEY, runtime_inputs.skip_startup_checks
        )


def _apply_tls_inputs(settings: Dynaconf, tls_inputs: Optional[TlsInputs]) -> None:
    if tls_inputs is None:
        return

    if tls_inputs.allow_insecure is not None:
        settings.set(RUNTIME_ALLOW_INSECURE_TLS_KEY, tls_inputs.allow_insecure)
    if tls_inputs.ca_bundle_path is not None:
        settings.set(
            RUNTIME_CA_BUNDLE_PATH_KEY, tls_inputs.ca_bundle_path.strip()
        )


def _apply_logging_inputs(
    settings: Dynaconf, logging_inputs: Optional[LoggingInputs]
) -> None:
    if logging_inputs is None:
        return

    kwargs = logging_inputs.as_kwargs()
    level_override = kwargs["level_override"]
    if level_override is not None:
        settings.set(LOGGING_LEVEL_KEY, level_override.strip())

    format_override = kwargs["format_override"]
    if format_override is not None:
        settings.set(LOGGING_FORMAT_KEY, format_override.strip())

    file_override = kwargs["file_override"]
    if file_override is not None:
        settings.set(LOGGING_FILE_KEY, file_override.strip())

    max_bytes_override = kwargs["max_bytes_override"]
    if max_bytes_override is not None:
        settings.set(LOGGING_MAX_BYTES_KEY, max_bytes_override)

    backup_count_override = kwargs["backup_count_override"]
    if backup_count_override is not None:
        settings.set(LOGGING_BACKUP_COUNT_KEY, backup_count_override)


def _apply_cli_overrides(
    settings: Dynaconf,
    *,
    api_key_input: Optional[str],
    subscription_inputs: Optional[SubscriptionInputs],
    runtime_inputs: Optional[RuntimeInputs],
    tls_inputs: Optional[TlsInputs],
    logging_inputs: Optional[LoggingInputs],
) -> None:
    _apply_api_key(settings, api_key_input)
    _apply_subscription_inputs(settings, subscription_inputs)
    _apply_runtime_inputs(settings, runtime_inputs)
    _apply_tls_inputs(settings, tls_inputs)
    _apply_logging_inputs(settings, logging_inputs)


def _build_dynaconf(config_path: Optional[str]) -> Dynaconf:
    files, root_path = _default_settings_files(config_path)
    settings = Dynaconf(
        settings_files=list(files),
        envvar_prefix="BIRRE",
        environments=False,
        load_dotenv=True,
        merge_enabled=True,
        root_path=root_path,
    )
    _apply_environment_overrides(settings)
    return settings


def load_settings(config_path: Optional[str] = None) -> Dynaconf:
    """Create a Dynaconf instance configured for the supplied path."""

    return _build_dynaconf(config_path)


def apply_cli_overrides(
    settings: Dynaconf,
    *,
    api_key_input: Optional[str] = None,
    subscription_inputs: Optional[SubscriptionInputs] = None,
    runtime_inputs: Optional[RuntimeInputs] = None,
    tls_inputs: Optional[TlsInputs] = None,
    logging_inputs: Optional[LoggingInputs] = None,
) -> None:
    """Apply CLI overrides to the provided settings instance."""

    _apply_cli_overrides(
        settings,
        api_key_input=api_key_input,
        subscription_inputs=subscription_inputs,
        runtime_inputs=runtime_inputs,
        tls_inputs=tls_inputs,
        logging_inputs=logging_inputs,
    )


def _resolve_context(settings: Dynaconf, warnings: list[str]) -> str:
    raw_context = _coerce_str(settings.get(ROLE_CONTEXT_KEY)) or "standard"
    normalized = raw_context.lower()
    if normalized not in _ALLOWED_CONTEXTS:
        warnings.append(
            f"Unknown context '{raw_context}' requested; defaulting to 'standard'"
        )
        return "standard"
    return normalized


def _resolve_risk_vector_filter(
    settings: Dynaconf, warnings: list[str]
) -> str:
    raw_filter = settings.get(ROLE_RISK_VECTOR_FILTER_KEY)
    normalized = _coerce_str(raw_filter)
    if not normalized:
        warnings.append(
            "Empty risk_vector_filter override; falling back to default configuration"
        )
        return DEFAULT_RISK_VECTOR_FILTER
    return normalized


def _resolve_max_findings(settings: Dynaconf, warnings: list[str]) -> int:
    candidate = settings.get(ROLE_MAX_FINDINGS_KEY)
    value = _coerce_int(candidate)
    if value is None or value <= 0:
        warnings.append(
            "Invalid max_findings override; using default configuration"
        )
        return DEFAULT_MAX_FINDINGS
    return value


def _resolve_bool(
    settings: Dynaconf, key: str, *, default: bool = False
) -> bool:
    value = settings.get(key)
    coerced = _coerce_bool(value)
    if coerced is None:
        return default
    return coerced


def _resolve_subscription_value(settings: Dynaconf, key: str) -> Optional[str]:
    return _coerce_str(settings.get(key))


def runtime_from_settings(settings: Dynaconf) -> Dict[str, Any]:
    """Extract runtime settings and validation messages from Dynaconf."""

    warnings: list[str] = []

    api_key = _coerce_str(settings.get(BITSIGHT_API_KEY_KEY))
    if not api_key:
        raise ValueError("BITSIGHT_API_KEY is required (config/env/CLI)")

    subscription_folder = _resolve_subscription_value(
        settings, BITSIGHT_SUBSCRIPTION_FOLDER_KEY
    )
    subscription_type = _resolve_subscription_value(
        settings, BITSIGHT_SUBSCRIPTION_TYPE_KEY
    )

    context = _resolve_context(settings, warnings)
    risk_vector_filter = _resolve_risk_vector_filter(settings, warnings)
    max_findings = _resolve_max_findings(settings, warnings)

    skip_startup_checks = _resolve_bool(
        settings, RUNTIME_SKIP_STARTUP_CHECKS_KEY, default=False
    )
    debug_enabled = _resolve_bool(settings, RUNTIME_DEBUG_KEY, default=False)
    allow_insecure_tls = _resolve_bool(
        settings, RUNTIME_ALLOW_INSECURE_TLS_KEY, default=False
    )
    ca_bundle_path = _coerce_str(settings.get(RUNTIME_CA_BUNDLE_PATH_KEY))

    if allow_insecure_tls and ca_bundle_path:
        warnings.append(
            "allow_insecure_tls takes precedence over ca_bundle_path; HTTPS verification will be disabled"
        )
        ca_bundle_path = None

    return {
        "api_key": api_key,
        "subscription_folder": subscription_folder,
        "subscription_type": subscription_type,
        "context": context,
        "risk_vector_filter": risk_vector_filter,
        "max_findings": max_findings,
        "skip_startup_checks": skip_startup_checks,
        "debug": debug_enabled,
        "allow_insecure_tls": allow_insecure_tls,
        "ca_bundle_path": ca_bundle_path,
        "warnings": warnings,
        "overrides": [],
    }


def logging_from_settings(settings: Dynaconf) -> LoggingSettings:
    """Extract logging configuration from Dynaconf."""

    level_value = _coerce_str(settings.get(LOGGING_LEVEL_KEY)) or DEFAULT_LOG_LEVEL
    format_value = (
        _coerce_str(settings.get(LOGGING_FORMAT_KEY)) or DEFAULT_LOG_FORMAT
    ).lower()
    if format_value not in {LOG_FORMAT_TEXT, LOG_FORMAT_JSON}:
        raise ValueError(f"Unsupported log format: {format_value}")

    file_path = _coerce_str(settings.get(LOGGING_FILE_KEY))

    max_bytes_value = _coerce_int(settings.get(LOGGING_MAX_BYTES_KEY))
    if max_bytes_value is None or max_bytes_value <= 0:
        max_bytes_value = DEFAULT_MAX_BYTES

    backup_count_value = _coerce_int(settings.get(LOGGING_BACKUP_COUNT_KEY))
    if backup_count_value is None or backup_count_value <= 0:
        backup_count_value = DEFAULT_BACKUP_COUNT

    mapping = logging.getLevelNamesMapping()
    level_upper = level_value.upper()
    if level_upper.isdigit():
        resolved_level = int(level_upper)
    else:
        resolved_level = mapping.get(level_upper, logging.INFO)

    return LoggingSettings(
        level=resolved_level,
        format=format_value,
        file_path=file_path,
        max_bytes=max_bytes_value,
        backup_count=backup_count_value,
    )


def resolve_birre_settings(
    *,
    api_key_input: Optional[str] = None,
    config_path: str = DEFAULT_CONFIG_FILENAME,
    subscription_inputs: Optional[SubscriptionInputs] = None,
    runtime_inputs: Optional[RuntimeInputs] = None,
    tls_inputs: Optional[TlsInputs] = None,
) -> Dict[str, Any]:
    settings = load_settings(config_path)
    apply_cli_overrides(
        settings,
        api_key_input=api_key_input,
        subscription_inputs=subscription_inputs,
        runtime_inputs=runtime_inputs,
        tls_inputs=tls_inputs,
    )
    return runtime_from_settings(settings)


def resolve_logging_settings(
    *,
    config_path: Optional[str] = None,
    level_override: Optional[str] = None,
    format_override: Optional[str] = None,
    file_override: Optional[str] = None,
    max_bytes_override: Optional[int] = None,
    backup_count_override: Optional[int] = None,
) -> LoggingSettings:
    settings = load_settings(config_path)
    apply_cli_overrides(
        settings,
        logging_inputs=LoggingInputs(
            level=level_override,
            format=format_override,
            file_path=file_override,
            max_bytes=max_bytes_override,
            backup_count=backup_count_override,
        ),
    )
    return logging_from_settings(settings)


def resolve_application_settings(
    *,
    api_key_input: Optional[str] = None,
    config_path: str = DEFAULT_CONFIG_FILENAME,
    subscription_inputs: Optional[SubscriptionInputs] = None,
    runtime_inputs: Optional[RuntimeInputs] = None,
    logging_inputs: Optional[LoggingInputs] = None,
    tls_inputs: Optional[TlsInputs] = None,
) -> Tuple[Dict[str, Any], LoggingSettings]:
    runtime_settings = resolve_birre_settings(
        api_key_input=api_key_input,
        config_path=config_path,
        subscription_inputs=subscription_inputs,
        runtime_inputs=runtime_inputs,
        tls_inputs=tls_inputs,
    )

    logging_inputs = logging_inputs or LoggingInputs()
    logging_settings = resolve_logging_settings(
        config_path=config_path,
        **logging_inputs.as_kwargs(),
    )

    if runtime_settings["debug"] and logging_settings.level > logging.DEBUG:
        logging_settings = LoggingSettings(
            level=logging.DEBUG,
            format=logging_settings.format,
            file_path=logging_settings.file_path,
            max_bytes=logging_settings.max_bytes,
            backup_count=logging_settings.backup_count,
        )

    return runtime_settings, logging_settings


settings = _build_dynaconf(None)


__all__ = [
    "DEFAULT_MAX_FINDINGS",
    "DEFAULT_RISK_VECTOR_FILTER",
    "DEFAULT_LOG_FORMAT",
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_BACKUP_COUNT",
    "LOG_FORMAT_TEXT",
    "LOG_FORMAT_JSON",
    "load_settings",
    "apply_cli_overrides",
    "runtime_from_settings",
    "logging_from_settings",
    "SubscriptionInputs",
    "RuntimeInputs",
    "TlsInputs",
    "LoggingInputs",
    "LoggingSettings",
    "resolve_birre_settings",
    "resolve_logging_settings",
    "resolve_application_settings",
    "settings",
]
