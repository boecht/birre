"""Utilities for resolving BiRRe configuration layers.

Values resolve with a simple precedence chain: command line inputs override
environment variables, which override the optional ``config.local.toml`` file,
which in turn overrides ``config.toml``. Blank strings are treated as "not
provided" so that lower-priority sources remain in effect.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import tomllib
from dotenv import load_dotenv

from .constants import (
    DEFAULT_CONFIG_FILENAME,
    LOCAL_CONFIG_FILENAME,
    coerce_bool,
)

BITSIGHT_SECTION = "bitsight"
RUNTIME_SECTION = "runtime"
ROLES_SECTION = "roles"
LOGGING_SECTION = "logging"

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

ENV_RISK_VECTOR_FILTER = "BIRRE_RISK_VECTOR_FILTER"
ENV_MAX_FINDINGS = "BIRRE_MAX_FINDINGS"

ENV_ALLOW_INSECURE_TLS = "BIRRE_ALLOW_INSECURE_TLS"
ENV_CA_BUNDLE = "BIRRE_CA_BUNDLE"

ENV_LOG_LEVEL = "BIRRE_LOG_LEVEL"
ENV_LOG_FORMAT = "BIRRE_LOG_FORMAT"
ENV_LOG_FILE = "BIRRE_LOG_FILE"
ENV_LOG_MAX_BYTES = "BIRRE_LOG_MAX_BYTES"
ENV_LOG_BACKUP_COUNT = "BIRRE_LOG_BACKUP_COUNT"

LOG_FORMAT_TEXT = "text"
LOG_FORMAT_JSON = "json"
DEFAULT_LOG_FORMAT = LOG_FORMAT_TEXT
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MAX_BYTES = 10_000_000
DEFAULT_BACKUP_COUNT = 5

SOURCE_LABELS = {
    "cli": "command line arguments",
    "env": "the environment",
    "local": "the local configuration file",
    "config": "the configuration file",
}


def _read_toml(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        return {}


def _merge_overlay(config_data: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    if not overlay:
        return dict(config_data)

    merged = dict(config_data)
    for section, values in overlay.items():
        if isinstance(values, dict) and isinstance(merged.get(section), dict):
            merged_section = dict(merged[section])
            merged_section.update(values)
            merged[section] = merged_section
        else:
            merged[section] = values
    return merged


def load_config_layers(base_path: str) -> Dict[str, Any]:
    """Return the primary configuration with any local overlay applied."""

    config_path = Path(base_path)
    config_data = _read_toml(config_path)
    local_path = config_path.with_name(f"{config_path.stem}.local{config_path.suffix}")
    local_data = _read_toml(local_path)
    return _merge_overlay(config_data, local_data)


def _load_layered_config(config_path: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    config_file = Path(config_path)
    config_data = _read_toml(config_file)
    local_file = config_file.with_name(f"{config_file.stem}.local{config_file.suffix}")
    local_data = _read_toml(local_file)
    return config_data, local_data


def _get_section(data: Dict[str, Any], name: str) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    section = data.get(name)
    if isinstance(section, dict):
        return section
    return {}


def _is_blank(value: object) -> bool:
    return isinstance(value, str) and not value.strip()


def _normalize_string(value: Optional[object]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_bool(value: Optional[object]) -> Optional[bool]:
    if value is None or _is_blank(value):
        return None
    return coerce_bool(value)


def _normalize_sources(
    sources: Sequence[Tuple[str, Optional[object]]],
    *,
    normalizer: Callable[[Optional[object]], Optional[object]],
) -> Tuple[List[Tuple[str, Optional[object]]], List[str]]:
    normalized: List[Tuple[str, Optional[object]]] = []
    blanks: List[str] = []
    for layer, raw in sources:
        if _is_blank(raw):
            blanks.append(layer)
            normalized.append((layer, None))
        else:
            normalized.append((layer, normalizer(raw)))
    return normalized, blanks


def _resolve_from_sources(
    normalized: Sequence[Tuple[str, Optional[object]]],
    *,
    default: Optional[object] = None,
) -> Tuple[Optional[object], Optional[str]]:
    for layer, value in normalized:
        if value is not None:
            return value, layer
    return default, None


def _join_labels(names: Iterable[str]) -> str:
    labels = [SOURCE_LABELS.get(name, name) for name in names]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _override_message(
    setting: str,
    normalized: Sequence[Tuple[str, Optional[object]]],
    chosen_layer: Optional[str],
) -> Optional[str]:
    if chosen_layer is None:
        return None

    chosen_index = next(
        (index for index, (layer, _) in enumerate(normalized) if layer == chosen_layer),
        None,
    )
    if chosen_index is None:
        return None

    overridden = [
        layer
        for layer, value in normalized[chosen_index + 1 :]
        if value is not None
    ]
    if not overridden:
        return None

    return (
        f"Using {setting} from {SOURCE_LABELS.get(chosen_layer, chosen_layer)}, "
        f"overriding values from {_join_labels(overridden)}."
    )


def _precedence_with_blank(
    normalized: Sequence[Tuple[str, Optional[object]]],
    blanks: Sequence[str],
    *,
    default: Optional[object],
    warning: Optional[str],
) -> Tuple[Optional[object], Optional[str], Optional[str]]:
    blank_set = set(blanks)
    for layer, value in normalized:
        if layer in blank_set:
            return default, warning, None
        if value is not None:
            return value, None, layer
    return default, None, None


def _coerce_positive_int(value: Optional[object]) -> int:
    if value is None:
        raise ValueError("Value must be provided")
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ValueError("Invalid integer value") from exc
    if integer <= 0:
        raise ValueError("Value must be positive")
    return integer


def _resolve_level(level_value: Optional[object]) -> int:
    mapping = logging.getLevelNamesMapping()
    if level_value is None:
        return mapping.get(DEFAULT_LOG_LEVEL, logging.INFO)
    if isinstance(level_value, int):
        return level_value
    text = str(level_value).strip()
    if not text:
        return mapping.get(DEFAULT_LOG_LEVEL, logging.INFO)
    upper = text.upper()
    if upper.isdigit():
        return int(upper)
    if upper not in mapping:
        raise ValueError(f"Unknown log level: {level_value}")
    return mapping[upper]


@dataclass(frozen=True)
class SubscriptionInputs:
    """Inputs that influence subscription resolution."""

    folder: Optional[str] = None
    type: Optional[str] = None


@dataclass(frozen=True)
class RuntimeInputs:
    """Inputs that influence runtime behaviour of the server."""

    context: Optional[str] = None
    debug: Optional[bool] = None
    risk_vector_filter: Optional[str] = None
    max_findings: Optional[int] = None
    skip_startup_checks: Optional[bool] = None


@dataclass(frozen=True)
class TlsInputs:
    """Inputs that control TLS verification behaviour."""

    allow_insecure: Optional[bool] = None
    ca_bundle_path: Optional[str] = None


@dataclass(frozen=True)
class LoggingInputs:
    """Inputs that influence logging configuration resolution."""

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


def resolve_birre_settings(
    *,
    api_key_input: Optional[str] = None,
    config_path: str = DEFAULT_CONFIG_FILENAME,
    subscription_inputs: Optional[SubscriptionInputs] = None,
    runtime_inputs: Optional[RuntimeInputs] = None,
    tls_inputs: Optional[TlsInputs] = None,
) -> Dict[str, Any]:
    """Resolve BiRRe runtime settings using config, env vars, and CLI overrides."""

    load_dotenv()

    config_data, local_data = _load_layered_config(config_path)

    bitsight_layers = {
        "config": _get_section(config_data, BITSIGHT_SECTION),
        "local": _get_section(local_data, BITSIGHT_SECTION),
    }
    runtime_layers = {
        "config": _get_section(config_data, RUNTIME_SECTION),
        "local": _get_section(local_data, RUNTIME_SECTION),
    }
    roles_layers = {
        "config": _get_section(config_data, ROLES_SECTION),
        "local": _get_section(local_data, ROLES_SECTION),
    }

    subscription_inputs = subscription_inputs or SubscriptionInputs()
    runtime_inputs = runtime_inputs or RuntimeInputs()
    tls_inputs = tls_inputs or TlsInputs()

    overrides: List[str] = []
    warnings: List[str] = []

    api_sources = [
        ("cli", api_key_input),
        ("env", os.getenv("BITSIGHT_API_KEY")),
        ("local", bitsight_layers["local"].get("api_key")),
        ("config", bitsight_layers["config"].get("api_key")),
    ]
    normalized_api, _ = _normalize_sources(api_sources, normalizer=_normalize_string)
    api_key, api_layer = _resolve_from_sources(normalized_api)
    if api_layer:
        message = _override_message("BITSIGHT_API_KEY", normalized_api, api_layer)
        if message:
            overrides.append(message)
    if not api_key:
        raise ValueError("BITSIGHT_API_KEY is required (config/env/CLI)")
    if api_layer == "config" and Path(config_path).name == DEFAULT_CONFIG_FILENAME:
        warnings.append(
            "Avoid storing bitsight.api_key in "
            f"{DEFAULT_CONFIG_FILENAME}; prefer {LOCAL_CONFIG_FILENAME}, environment variables, or CLI overrides."
        )

    folder_sources = [
        ("cli", subscription_inputs.folder),
        ("env", os.getenv("BIRRE_SUBSCRIPTION_FOLDER")),
        ("local", bitsight_layers["local"].get("subscription_folder")),
        ("config", bitsight_layers["config"].get("subscription_folder")),
    ]
    normalized_folder, _ = _normalize_sources(
        folder_sources, normalizer=_normalize_string
    )
    subscription_folder, folder_layer = _resolve_from_sources(normalized_folder)
    if folder_layer:
        message = _override_message("SUBSCRIPTION_FOLDER", normalized_folder, folder_layer)
        if message:
            overrides.append(message)

    type_sources = [
        ("cli", subscription_inputs.type),
        ("env", os.getenv("BIRRE_SUBSCRIPTION_TYPE")),
        ("local", bitsight_layers["local"].get("subscription_type")),
        ("config", bitsight_layers["config"].get("subscription_type")),
    ]
    normalized_type, _ = _normalize_sources(type_sources, normalizer=_normalize_string)
    subscription_type, type_layer = _resolve_from_sources(normalized_type)
    if type_layer:
        message = _override_message("SUBSCRIPTION_TYPE", normalized_type, type_layer)
        if message:
            overrides.append(message)

    context_sources = [
        ("cli", runtime_inputs.context),
        ("env", os.getenv("BIRRE_CONTEXT")),
        ("local", roles_layers["local"].get("context")),
        ("config", roles_layers["config"].get("context")),
    ]
    normalized_context, _ = _normalize_sources(
        context_sources, normalizer=_normalize_string
    )
    context_value, context_layer = _resolve_from_sources(
        normalized_context, default="standard"
    )
    context_warning = None
    if context_value is None:
        normalized_context_value = "standard"
    else:
        candidate = context_value.lower()
        if candidate in {"standard", "risk_manager"}:
            normalized_context_value = candidate
        else:
            normalized_context_value = "standard"
            context_warning = (
                f"Unknown context '{context_value}' requested; defaulting to 'standard'"
            )
    if context_warning:
        warnings.append(context_warning)
    elif context_layer:
        message = _override_message("CONTEXT", normalized_context, context_layer)
        if message:
            overrides.append(message)

    skip_sources = [
        ("cli", runtime_inputs.skip_startup_checks),
        ("env", os.getenv("BIRRE_SKIP_STARTUP_CHECKS")),
        ("local", runtime_layers["local"].get("skip_startup_checks")),
        ("config", runtime_layers["config"].get("skip_startup_checks")),
    ]
    normalized_skip, _ = _normalize_sources(skip_sources, normalizer=_normalize_bool)
    skip_startup_checks, skip_layer = _resolve_from_sources(
        normalized_skip, default=False
    )
    if skip_layer:
        message = _override_message("SKIP_STARTUP_CHECKS", normalized_skip, skip_layer)
        if message:
            overrides.append(message)

    debug_env = os.getenv("BIRRE_DEBUG") or os.getenv("DEBUG")
    debug_sources = [
        ("cli", runtime_inputs.debug),
        ("env", debug_env),
        ("local", runtime_layers["local"].get("debug")),
        ("config", runtime_layers["config"].get("debug")),
    ]
    normalized_debug, _ = _normalize_sources(debug_sources, normalizer=_normalize_bool)
    debug_enabled, debug_layer = _resolve_from_sources(normalized_debug, default=False)
    if debug_layer:
        message = _override_message("DEBUG", normalized_debug, debug_layer)
        if message:
            overrides.append(message)

    risk_sources = [
        ("cli", runtime_inputs.risk_vector_filter),
        ("env", os.getenv(ENV_RISK_VECTOR_FILTER)),
        ("local", roles_layers["local"].get("risk_vector_filter")),
        ("config", roles_layers["config"].get("risk_vector_filter")),
    ]
    normalized_risk, risk_blanks = _normalize_sources(
        risk_sources, normalizer=_normalize_string
    )
    risk_vector_filter, risk_warning, risk_layer = _precedence_with_blank(
        normalized_risk,
        risk_blanks,
        default=DEFAULT_RISK_VECTOR_FILTER,
        warning="Empty risk_vector_filter override; falling back to default configuration",
    )
    if risk_warning:
        warnings.append(risk_warning)
    elif risk_layer:
        message = _override_message("RISK_VECTOR_FILTER", normalized_risk, risk_layer)
        if message:
            overrides.append(message)

    tls_sources = [
        ("cli", tls_inputs.allow_insecure),
        ("env", os.getenv(ENV_ALLOW_INSECURE_TLS)),
        ("local", runtime_layers["local"].get("allow_insecure_tls")),
        ("config", runtime_layers["config"].get("allow_insecure_tls")),
    ]
    normalized_tls, _ = _normalize_sources(tls_sources, normalizer=_normalize_bool)
    allow_insecure_tls, allow_insecure_layer = _resolve_from_sources(
        normalized_tls, default=False
    )
    if allow_insecure_layer:
        message = _override_message("ALLOW_INSECURE_TLS", normalized_tls, allow_insecure_layer)
        if message:
            overrides.append(message)

    ca_sources = [
        ("cli", tls_inputs.ca_bundle_path),
        ("env", os.getenv(ENV_CA_BUNDLE)),
        ("local", runtime_layers["local"].get("ca_bundle_path")),
        ("config", runtime_layers["config"].get("ca_bundle_path")),
    ]
    normalized_ca, ca_blanks = _normalize_sources(ca_sources, normalizer=_normalize_string)
    ca_bundle_path, ca_warning, ca_layer = _precedence_with_blank(
        normalized_ca,
        ca_blanks,
        default=None,
        warning="Empty ca_bundle_path override; ignoring custom CA bundle configuration",
    )
    if ca_warning:
        warnings.append(ca_warning)
    elif ca_layer:
        message = _override_message("CA_BUNDLE_PATH", normalized_ca, ca_layer)
        if message:
            overrides.append(message)

    if allow_insecure_tls and ca_bundle_path:
        warnings.append(
            "allow_insecure_tls takes precedence over ca_bundle_path; HTTPS verification will be disabled"
        )
        ca_bundle_path = None

    max_sources = [
        ("cli", runtime_inputs.max_findings),
        ("env", os.getenv(ENV_MAX_FINDINGS)),
        ("local", roles_layers["local"].get("max_findings")),
        ("config", roles_layers["config"].get("max_findings")),
    ]
    normalized_max, _ = _normalize_sources(max_sources, normalizer=_normalize_string)
    raw_max, max_layer = _resolve_from_sources(normalized_max)
    try:
        max_findings = _coerce_positive_int(raw_max) if raw_max is not None else DEFAULT_MAX_FINDINGS
        if raw_max is None:
            max_layer = None
    except ValueError:
        warnings.append("Invalid max_findings override; using default configuration")
        max_findings = DEFAULT_MAX_FINDINGS
        max_layer = None
    if max_layer:
        message = _override_message("MAX_FINDINGS", normalized_max, max_layer)
        if message:
            overrides.append(message)

    return {
        "api_key": api_key,
        "subscription_folder": subscription_folder,
        "subscription_type": subscription_type,
        "context": normalized_context_value,
        "risk_vector_filter": risk_vector_filter,
        "max_findings": max_findings,
        "skip_startup_checks": bool(skip_startup_checks),
        "debug": bool(debug_enabled),
        "allow_insecure_tls": bool(allow_insecure_tls),
        "ca_bundle_path": ca_bundle_path,
        "warnings": warnings,
        "overrides": overrides,
    }


def resolve_logging_settings(
    *,
    config_path: Optional[str] = None,
    level_override: Optional[str] = None,
    format_override: Optional[str] = None,
    file_override: Optional[str] = None,
    max_bytes_override: Optional[int] = None,
    backup_count_override: Optional[int] = None,
) -> LoggingSettings:
    config_section: Dict[str, Any] = {}
    local_section: Dict[str, Any] = {}
    if config_path:
        config_data, local_data = _load_layered_config(config_path)
        config_section = _get_section(config_data, LOGGING_SECTION)
        local_section = _get_section(local_data, LOGGING_SECTION)

    level_sources = [
        ("cli", level_override),
        ("env", os.getenv(ENV_LOG_LEVEL)),
        ("local", local_section.get("level")),
        ("config", config_section.get("level")),
    ]
    normalized_level, _ = _normalize_sources(level_sources, normalizer=_normalize_string)
    level_value, _ = _resolve_from_sources(
        normalized_level, default=DEFAULT_LOG_LEVEL
    )

    format_sources = [
        ("cli", format_override),
        ("env", os.getenv(ENV_LOG_FORMAT)),
        ("local", local_section.get("format")),
        ("config", config_section.get("format")),
    ]
    normalized_format, _ = _normalize_sources(format_sources, normalizer=_normalize_string)
    format_value, _ = _resolve_from_sources(
        normalized_format, default=DEFAULT_LOG_FORMAT
    )

    file_sources = [
        ("cli", file_override),
        ("env", os.getenv(ENV_LOG_FILE)),
        ("local", local_section.get("file")),
        ("config", config_section.get("file")),
    ]
    normalized_file, _ = _normalize_sources(file_sources, normalizer=_normalize_string)
    file_path, _ = _resolve_from_sources(normalized_file)

    max_bytes_sources = [
        ("cli", max_bytes_override),
        ("env", os.getenv(ENV_LOG_MAX_BYTES)),
        ("local", local_section.get("max_bytes")),
        ("config", config_section.get("max_bytes")),
    ]
    normalized_max_bytes, _ = _normalize_sources(max_bytes_sources, normalizer=_normalize_string)
    raw_max_bytes, _ = _resolve_from_sources(
        normalized_max_bytes, default=str(DEFAULT_MAX_BYTES)
    )

    backup_sources = [
        ("cli", backup_count_override),
        ("env", os.getenv(ENV_LOG_BACKUP_COUNT)),
        ("local", local_section.get("backup_count")),
        ("config", config_section.get("backup_count")),
    ]
    normalized_backup, _ = _normalize_sources(backup_sources, normalizer=_normalize_string)
    raw_backup_count, _ = _resolve_from_sources(
        normalized_backup, default=str(DEFAULT_BACKUP_COUNT)
    )

    level_number = _resolve_level(level_value)

    if not isinstance(format_value, str):
        raise ValueError("Log format must resolve to a string")
    resolved_format = format_value.lower()
    if resolved_format not in {LOG_FORMAT_TEXT, LOG_FORMAT_JSON}:
        raise ValueError(f"Unsupported log format: {format_value}")

    try:
        max_bytes = _coerce_positive_int(raw_max_bytes)
    except ValueError:
        raise ValueError("Invalid max_bytes value") from None

    try:
        backup_count = _coerce_positive_int(raw_backup_count)
    except ValueError:
        raise ValueError("Invalid backup_count value") from None

    return LoggingSettings(
        level=level_number,
        format=resolved_format,
        file_path=file_path,
        max_bytes=max_bytes,
        backup_count=backup_count,
    )


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
    logging_kwargs = logging_inputs.as_kwargs() if logging_inputs else {}
    logging_settings = resolve_logging_settings(
        config_path=config_path,
        **logging_kwargs,
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


__all__ = [
    "resolve_birre_settings",
    "resolve_logging_settings",
    "resolve_application_settings",
    "load_config_layers",
    "SubscriptionInputs",
    "RuntimeInputs",
    "TlsInputs",
    "LoggingInputs",
    "LoggingSettings",
    "LOG_FORMAT_TEXT",
    "LOG_FORMAT_JSON",
    "DEFAULT_RISK_VECTOR_FILTER",
    "DEFAULT_MAX_FINDINGS",
    "ENV_ALLOW_INSECURE_TLS",
    "ENV_CA_BUNDLE",
]
