"""Configuration helpers for the BiRRe server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

import logging
import tomllib
from dotenv import load_dotenv

from .constants import (
    DEFAULT_CONFIG_FILENAME,
    LOCAL_CONFIG_FILENAME,
    coerce_bool,
)

BITSIGHT_SECTION = "bitsight"

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

ENV_RISK_VECTOR_FILTER = "BIRRE_RISK_VECTOR_FILTER"
DEFAULT_MAX_FINDINGS = 10
ENV_MAX_FINDINGS = "BIRRE_MAX_FINDINGS"

LOG_FORMAT_TEXT = "text"
LOG_FORMAT_JSON = "json"
DEFAULT_LOG_FORMAT = LOG_FORMAT_TEXT
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MAX_BYTES = 10_000_000
DEFAULT_BACKUP_COUNT = 5

ENV_ALLOW_INSECURE_TLS = "BIRRE_ALLOW_INSECURE_TLS"
ENV_CA_BUNDLE = "BIRRE_CA_BUNDLE"

ENV_LOG_LEVEL = "BIRRE_LOG_LEVEL"
ENV_LOG_FORMAT = "BIRRE_LOG_FORMAT"
ENV_LOG_FILE = "BIRRE_LOG_FILE"
ENV_LOG_MAX_BYTES = "BIRRE_LOG_MAX_BYTES"
ENV_LOG_BACKUP_COUNT = "BIRRE_LOG_BACKUP_COUNT"


def _load_config(path: str) -> Dict[str, Any]:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}


def _apply_overlay_section(
    base: Dict[str, Any],
    section: str,
    values: Any,
) -> None:
    """Apply a section from a local overlay configuration to the base config."""

    if not isinstance(values, dict):
        base[section] = values
        return

    base_section = base.get(section)
    if not isinstance(base_section, dict):
        base_section = {}
    base[section] = {**base_section, **values}


def load_config_layers(base_path: str) -> Dict[str, Any]:
    cfg = _load_config(base_path)
    path_obj = Path(base_path)
    local_path = path_obj.with_name(f"{path_obj.stem}.local{path_obj.suffix}")

    if not local_path.exists():
        return cfg

    overlay = _load_config(str(local_path))

    if not isinstance(cfg, dict) or not isinstance(overlay, dict):
        return overlay or cfg

    for section, values in overlay.items():
        _apply_overlay_section(cfg, section, values)

    return cfg


def _get_dict_section(cfg: Any, section: str) -> Dict[str, Any]:
    if isinstance(cfg, dict):
        candidate = cfg.get(section)
        if isinstance(candidate, dict):
            return candidate
    return {}


def _load_base_config(config_path: str) -> Dict[str, Any]:
    if config_path.endswith(DEFAULT_CONFIG_FILENAME):
        return _load_config(config_path)
    return {}


def _load_local_config(config_path: str) -> Dict[str, Any]:
    path_obj = Path(config_path)
    local_path = path_obj.with_name(f"{path_obj.stem}.local{path_obj.suffix}")
    if not local_path.exists():
        return {}
    return _load_config(str(local_path))


def _first_truthy(*values: Optional[Any]) -> Optional[Any]:
    for value in values:
        if value:
            return value
    return None


def _value_provided(value: Optional[Any]) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _normalize_optional_str(value: Optional[Any]) -> Optional[str]:
    """Normalize optional string-like inputs by trimming whitespace."""

    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None


def _string_was_blank(value: Optional[Any]) -> bool:
    if value is None:
        return False
    return str(value).strip() == ""


def _join_sources(names: Sequence[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


_SOURCE_LABELS = {
    "cli": "command line arguments",
    "env": "the environment",
    "local": "the local configuration file",
    "base": "the default configuration file",
}


def _record_override_message(
    messages: list[str],
    setting: str,
    *,
    cli_value: Optional[Any] = None,
    env_value: Optional[Any] = None,
    local_config_value: Optional[Any] = None,
    base_config_value: Optional[Any] = None,
) -> None:
    sources = [
        ("cli", cli_value),
        ("env", env_value),
        ("local", local_config_value),
        ("base", base_config_value),
    ]

    for index, (key, value) in enumerate(sources):
        if not _value_provided(value):
            continue

        overridden_keys = [
            source_key
            for source_key, candidate in sources[index + 1 :]
            if _value_provided(candidate)
        ]
        if not overridden_keys:
            return

        chosen_label = _SOURCE_LABELS[key]
        overridden_labels = [_SOURCE_LABELS[k] for k in overridden_keys]
        overridden_phrase = _join_sources(overridden_labels)
        messages.append(
            f"Using {setting} from {chosen_label}, overriding values from {overridden_phrase}."
        )
        return


def _resolve_bool_chain(*values: Optional[Any], default: bool = False) -> bool:
    result = default
    for value in values:
        result = coerce_bool(value, default=result)
    return result


def _resolve_context_value(
    context_arg: Optional[str],
    context_env: Optional[str],
    context_cfg: Optional[Any],
) -> Tuple[str, Optional[str]]:
    requested = _first_truthy(context_arg, context_env, context_cfg)
    normalized, invalid, candidate = _normalize_context(requested)
    if invalid:
        return normalized, (
            f"Unknown context '{candidate}' requested; defaulting to 'standard'"
        )
    return normalized, None


def _resolve_risk_vector_filter(
    arg_value: Optional[str],
    arg_blank: bool,
    env_value: Optional[str],
    env_blank: bool,
    cfg_value: Optional[str],
    cfg_blank: bool,
) -> Tuple[str, Optional[str]]:
    for value, was_blank in (
        (arg_value, arg_blank),
        (env_value, env_blank),
        (cfg_value, cfg_blank),
    ):
        if was_blank:
            return DEFAULT_RISK_VECTOR_FILTER, (
                "Empty risk_vector_filter override; falling back to default configuration"
            )
        if value is not None:
            return value, None

    return DEFAULT_RISK_VECTOR_FILTER, None


def _resolve_ca_bundle_path(
    arg_value: Optional[str],
    arg_blank: bool,
    env_value: Optional[str],
    env_blank: bool,
    cfg_value: Optional[str],
    cfg_blank: bool,
) -> Tuple[Optional[str], Optional[str]]:
    for value, was_blank in (
        (arg_value, arg_blank),
        (env_value, env_blank),
        (cfg_value, cfg_blank),
    ):
        if was_blank:
            return None, (
                "Empty ca_bundle_path override; ignoring custom CA bundle configuration"
            )
        if value is not None:
            return value, None

    return None, None


def _resolve_max_findings(
    arg_value: Optional[int],
    env_value: Optional[str],
    cfg_value: Optional[Any],
) -> Tuple[int, Optional[str]]:
    for candidate in (arg_value, env_value, cfg_value):
        if candidate is not None:
            raw = candidate
            break
    else:
        raw = None

    try:
        return _coerce_positive_int(raw, DEFAULT_MAX_FINDINGS), None
    except ValueError:
        return DEFAULT_MAX_FINDINGS, (
            "Invalid max_findings override; using default configuration"
        )


def _normalize_context(value: Optional[object]) -> tuple[str, bool, object]:
    raw = value if value not in (None, "") else None
    candidate: object = raw if raw is not None else "standard"
    normalized = str(candidate).strip().lower()
    if normalized in {"standard", "risk_manager"}:
        return normalized, False, candidate
    return "standard", raw is not None, candidate


def _resolve_level(level_value: Optional[str]) -> int:
    mapping = logging.getLevelNamesMapping()
    if level_value is None:
        return mapping.get(DEFAULT_LOG_LEVEL, logging.INFO)
    if isinstance(level_value, int):
        return level_value
    upper = str(level_value).upper()
    if upper.isdigit():
        return int(upper)
    if upper not in mapping:
        raise ValueError(f"Unknown log level: {level_value}")
    return mapping[upper]


def _coerce_positive_int(candidate: Optional[Any], default: int) -> int:
    if candidate is None:
        return default
    try:
        value = int(candidate)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid integer value: {candidate}") from exc
    if value <= 0:
        raise ValueError(f"Value must be positive: {candidate}")
    return value


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
        """Map provided values to ``resolve_logging_settings`` keyword arguments."""

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

    cfg = load_config_layers(config_path)
    base_cfg = _load_base_config(config_path)
    local_cfg = _load_local_config(config_path)
    base_bitsight_cfg = _get_dict_section(base_cfg, BITSIGHT_SECTION)
    local_bitsight_cfg = _get_dict_section(local_cfg, BITSIGHT_SECTION)

    bitsight_cfg = _get_dict_section(cfg, BITSIGHT_SECTION)
    runtime_cfg = _get_dict_section(cfg, "runtime")
    base_runtime_cfg = _get_dict_section(base_cfg, "runtime")
    local_runtime_cfg = _get_dict_section(local_cfg, "runtime")

    api_key_cfg = _normalize_optional_str(bitsight_cfg.get("api_key"))
    local_api_key_cfg = _normalize_optional_str(local_bitsight_cfg.get("api_key"))
    base_api_key_cfg = _normalize_optional_str(base_bitsight_cfg.get("api_key"))

    folder_cfg = _normalize_optional_str(bitsight_cfg.get("subscription_folder"))
    type_cfg = _normalize_optional_str(bitsight_cfg.get("subscription_type"))
    local_folder_cfg = _normalize_optional_str(
        local_bitsight_cfg.get("subscription_folder")
    )
    local_type_cfg = _normalize_optional_str(local_bitsight_cfg.get("subscription_type"))
    base_folder_cfg = _normalize_optional_str(
        base_bitsight_cfg.get("subscription_folder")
    )
    base_type_cfg = _normalize_optional_str(base_bitsight_cfg.get("subscription_type"))

    startup_skip_cfg = runtime_cfg.get("skip_startup_checks")
    debug_cfg = runtime_cfg.get("debug")
    context_cfg_raw = runtime_cfg.get("context")
    context_cfg = _normalize_optional_str(context_cfg_raw)
    risk_filter_cfg_raw = runtime_cfg.get("risk_vector_filter")
    risk_filter_cfg = _normalize_optional_str(risk_filter_cfg_raw)
    risk_filter_cfg_blank = _string_was_blank(risk_filter_cfg_raw)
    max_findings_cfg = runtime_cfg.get("max_findings")
    allow_insecure_cfg = runtime_cfg.get("allow_insecure_tls")
    ca_bundle_cfg_raw = runtime_cfg.get("ca_bundle_path")
    ca_bundle_cfg = _normalize_optional_str(ca_bundle_cfg_raw)
    ca_bundle_cfg_blank = _string_was_blank(ca_bundle_cfg_raw)

    api_key_env = _normalize_optional_str(os.getenv("BITSIGHT_API_KEY"))
    folder_env = _normalize_optional_str(os.getenv("BIRRE_SUBSCRIPTION_FOLDER"))
    type_env = _normalize_optional_str(os.getenv("BIRRE_SUBSCRIPTION_TYPE"))
    startup_skip_env = os.getenv("BIRRE_SKIP_STARTUP_CHECKS")
    debug_env = os.getenv("BIRRE_DEBUG") or os.getenv("DEBUG")
    context_env_raw = os.getenv("BIRRE_CONTEXT")
    context_env = _normalize_optional_str(context_env_raw)
    risk_filter_env_raw = os.getenv(ENV_RISK_VECTOR_FILTER)
    risk_filter_env = _normalize_optional_str(risk_filter_env_raw)
    risk_filter_env_blank = _string_was_blank(risk_filter_env_raw)
    max_findings_env = os.getenv(ENV_MAX_FINDINGS)
    allow_insecure_env = os.getenv(ENV_ALLOW_INSECURE_TLS)
    ca_bundle_env_raw = os.getenv(ENV_CA_BUNDLE)
    ca_bundle_env = _normalize_optional_str(ca_bundle_env_raw)
    ca_bundle_env_blank = _string_was_blank(ca_bundle_env_raw)

    subscription_inputs = subscription_inputs or SubscriptionInputs()
    runtime_inputs = runtime_inputs or RuntimeInputs()
    tls_inputs = tls_inputs or TlsInputs()

    local_context_cfg = _normalize_optional_str(local_runtime_cfg.get("context"))
    base_context_cfg = _normalize_optional_str(base_runtime_cfg.get("context"))
    local_risk_filter_cfg = _normalize_optional_str(
        local_runtime_cfg.get("risk_vector_filter")
    )
    base_risk_filter_cfg = _normalize_optional_str(
        base_runtime_cfg.get("risk_vector_filter")
    )

    override_logs: list[str] = []

    api_key_cli = _normalize_optional_str(api_key_input)
    api_key = _first_truthy(
        api_key_cli,
        api_key_env,
        local_api_key_cfg,
        api_key_cfg,
        base_api_key_cfg,
    )
    _record_override_message(
        override_logs,
        "BITSIGHT_API_KEY",
        cli_value=api_key_cli,
        env_value=api_key_env,
        local_config_value=local_api_key_cfg,
        base_config_value=base_api_key_cfg,
    )
    cli_folder = _normalize_optional_str(subscription_inputs.folder)
    cli_type = _normalize_optional_str(subscription_inputs.type)

    subscription_folder = _first_truthy(
        cli_folder,
        folder_env,
        local_folder_cfg,
        folder_cfg,
        base_folder_cfg,
    )
    _record_override_message(
        override_logs,
        "SUBSCRIPTION_FOLDER",
        cli_value=cli_folder,
        env_value=folder_env,
        local_config_value=local_folder_cfg,
        base_config_value=base_folder_cfg,
    )
    subscription_type = _first_truthy(
        cli_type,
        type_env,
        local_type_cfg,
        type_cfg,
        base_type_cfg,
    )
    _record_override_message(
        override_logs,
        "SUBSCRIPTION_TYPE",
        cli_value=cli_type,
        env_value=type_env,
        local_config_value=local_type_cfg,
        base_config_value=base_type_cfg,
    )

    cli_context = _normalize_optional_str(runtime_inputs.context)
    effective_context_cfg = context_cfg if context_cfg is not None else base_context_cfg
    normalized_context, context_warning = _resolve_context_value(
        cli_context, context_env, effective_context_cfg
    )

    warnings = []
    if context_warning is None:
        _record_override_message(
            override_logs,
            "CONTEXT",
            cli_value=cli_context,
            env_value=context_env,
            local_config_value=local_context_cfg,
            base_config_value=base_context_cfg,
        )
    else:
        warnings.append(context_warning)

    if base_api_key_cfg is not None:
        warnings.append(
            "Avoid storing bitsight.api_key in "
            f"{DEFAULT_CONFIG_FILENAME}; prefer {LOCAL_CONFIG_FILENAME}, environment variables, or CLI overrides."
        )

    skip_startup_checks = _resolve_bool_chain(
        startup_skip_cfg, startup_skip_env, runtime_inputs.skip_startup_checks
    )
    _record_override_message(
        override_logs,
        "SKIP_STARTUP_CHECKS",
        cli_value=runtime_inputs.skip_startup_checks,
        env_value=startup_skip_env,
        local_config_value=local_runtime_cfg.get("skip_startup_checks"),
        base_config_value=base_runtime_cfg.get("skip_startup_checks"),
    )

    debug_enabled = _resolve_bool_chain(
        debug_cfg, debug_env, runtime_inputs.debug
    )
    _record_override_message(
        override_logs,
        "DEBUG",
        cli_value=runtime_inputs.debug,
        env_value=debug_env,
        local_config_value=local_runtime_cfg.get("debug"),
        base_config_value=base_runtime_cfg.get("debug"),
    )

    cli_risk_filter = _normalize_optional_str(runtime_inputs.risk_vector_filter)
    cli_risk_blank = _string_was_blank(runtime_inputs.risk_vector_filter)
    risk_vector_filter, risk_warning = _resolve_risk_vector_filter(
        cli_risk_filter,
        cli_risk_blank,
        risk_filter_env,
        risk_filter_env_blank,
        risk_filter_cfg,
        risk_filter_cfg_blank,
    )
    if risk_warning:
        warnings.append(risk_warning)
    else:
        _record_override_message(
            override_logs,
            "RISK_VECTOR_FILTER",
            cli_value=cli_risk_filter,
            env_value=risk_filter_env,
            local_config_value=local_risk_filter_cfg,
            base_config_value=base_risk_filter_cfg,
        )

    allow_insecure_tls = _resolve_bool_chain(
        allow_insecure_cfg,
        allow_insecure_env,
        tls_inputs.allow_insecure,
    )
    _record_override_message(
        override_logs,
        "ALLOW_INSECURE_TLS",
        cli_value=tls_inputs.allow_insecure,
        env_value=allow_insecure_env,
        local_config_value=local_runtime_cfg.get("allow_insecure_tls"),
        base_config_value=base_runtime_cfg.get("allow_insecure_tls"),
    )

    cli_ca_bundle = _normalize_optional_str(tls_inputs.ca_bundle_path)
    cli_ca_blank = _string_was_blank(tls_inputs.ca_bundle_path)
    ca_bundle_path, ca_warning = _resolve_ca_bundle_path(
        cli_ca_bundle,
        cli_ca_blank,
        ca_bundle_env,
        ca_bundle_env_blank,
        ca_bundle_cfg,
        ca_bundle_cfg_blank,
    )
    if ca_warning:
        warnings.append(ca_warning)
    else:
        _record_override_message(
            override_logs,
            "CA_BUNDLE_PATH",
            cli_value=tls_inputs.ca_bundle_path,
            env_value=ca_bundle_env,
            local_config_value=local_runtime_cfg.get("ca_bundle_path"),
            base_config_value=base_runtime_cfg.get("ca_bundle_path"),
        )

    if allow_insecure_tls and ca_bundle_path:
        warnings.append(
            "allow_insecure_tls takes precedence over ca_bundle_path; HTTPS verification will be disabled"
        )
        ca_bundle_path = None

    max_findings, max_warning = _resolve_max_findings(
        runtime_inputs.max_findings, max_findings_env, max_findings_cfg
    )
    if max_warning:
        warnings.append(max_warning)
    else:
        _record_override_message(
            override_logs,
            "MAX_FINDINGS",
            cli_value=runtime_inputs.max_findings,
            env_value=max_findings_env,
            local_config_value=local_runtime_cfg.get("max_findings"),
            base_config_value=base_runtime_cfg.get("max_findings"),
        )

    # Environment variables are not mutated; downstream consumers rely on returned settings.

    if not api_key:
        raise ValueError("BITSIGHT_API_KEY is required (config/env/CLI)")

    return {
        "api_key": api_key,
        "subscription_folder": subscription_folder,
        "subscription_type": subscription_type,
        "context": normalized_context,
        "risk_vector_filter": risk_vector_filter,
        "max_findings": max_findings,
        "skip_startup_checks": skip_startup_checks,
        "debug": debug_enabled,
        "allow_insecure_tls": allow_insecure_tls,
        "ca_bundle_path": ca_bundle_path,
        "warnings": warnings,
        "overrides": override_logs,
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
    config_section = {}
    if config_path:
        data = load_config_layers(config_path)
        if isinstance(data, dict):
            candidate = data.get("logging", {})
            if isinstance(candidate, dict):
                config_section = candidate

    level_value = (
        level_override
        or os.getenv(ENV_LOG_LEVEL)
        or config_section.get("level")
        or DEFAULT_LOG_LEVEL
    )
    format_value = (
        _normalize_optional_str(format_override)
        or _normalize_optional_str(os.getenv(ENV_LOG_FORMAT))
        or _normalize_optional_str(config_section.get("format"))
        or DEFAULT_LOG_FORMAT
    )

    file_path = (
        _normalize_optional_str(file_override)
        or _normalize_optional_str(os.getenv(ENV_LOG_FILE))
        or _normalize_optional_str(config_section.get("file"))
    )

    max_bytes_value = (
        max_bytes_override
        or os.getenv(ENV_LOG_MAX_BYTES)
        or config_section.get("max_bytes")
    )
    backup_count_value = (
        backup_count_override
        or os.getenv(ENV_LOG_BACKUP_COUNT)
        or config_section.get("backup_count")
    )

    resolved_level = _resolve_level(level_value)
    resolved_format = format_value.lower()
    if resolved_format not in {LOG_FORMAT_TEXT, LOG_FORMAT_JSON}:
        raise ValueError(f"Unsupported log format: {format_value}")

    resolved_max_bytes = _coerce_positive_int(max_bytes_value, DEFAULT_MAX_BYTES)
    resolved_backup_count = _coerce_positive_int(
        backup_count_value, DEFAULT_BACKUP_COUNT
    )

    return LoggingSettings(
        level=resolved_level,
        format=resolved_format,
        file_path=file_path,
        max_bytes=resolved_max_bytes,
        backup_count=resolved_backup_count,
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
    logging_kwargs = (
        logging_inputs.as_kwargs() if logging_inputs is not None else {}
    )
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
