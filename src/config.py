"""Configuration helpers for the BiRRe server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import logging
import tomllib
from dotenv import load_dotenv

from .constants import coerce_bool

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


def load_config_layers(base_path: str) -> Dict[str, Any]:
    cfg = _load_config(base_path)
    p = Path(base_path)
    local_path = p.with_name(f"{p.stem}.local{p.suffix}")
    if local_path.exists():
        overlay = _load_config(str(local_path))
        if isinstance(cfg, dict) and isinstance(overlay, dict):
            for section, values in overlay.items():
                if isinstance(values, dict):
                    base_section = (
                        cfg.get(section, {})
                        if isinstance(cfg.get(section), dict)
                        else {}
                    )
                    cfg[section] = {**base_section, **values}
                else:
                    cfg[section] = values
        else:
            cfg = overlay or cfg
    return cfg


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
    api_key_arg: Optional[str] = None,
    config_path: str = "config.toml",
    subscription_folder_arg: Optional[str] = None,
    subscription_type_arg: Optional[str] = None,
    context_arg: Optional[str] = None,
    debug_arg: Optional[bool] = None,
    risk_vector_filter_arg: Optional[str] = None,
    max_findings_arg: Optional[int] = None,
) -> Dict[str, Any]:
    """Resolve BiRRe runtime settings using config, env vars, and CLI overrides."""

    load_dotenv()

    cfg = load_config_layers(config_path)
    base_cfg = _load_config(config_path) if config_path.endswith("config.toml") else {}
    base_bitsight_cfg = (
        base_cfg.get("bitsight", {}) if isinstance(base_cfg, dict) else {}
    )

    bitsight_cfg = cfg.get("bitsight", {}) if isinstance(cfg, dict) else {}
    runtime_cfg = (
        cfg.get("runtime")
        if isinstance(cfg, dict) and isinstance(cfg.get("runtime"), dict)
        else {}
    )

    base_api_key_cfg = (
        base_bitsight_cfg.get("api_key")
        if isinstance(base_bitsight_cfg, dict)
        else None
    )
    api_key_cfg = (
        bitsight_cfg.get("api_key") if isinstance(bitsight_cfg, dict) else None
    )
    folder_cfg = (
        bitsight_cfg.get("subscription_folder")
        if isinstance(bitsight_cfg, dict)
        else None
    )
    type_cfg = (
        bitsight_cfg.get("subscription_type")
        if isinstance(bitsight_cfg, dict)
        else None
    )

    startup_skip_cfg = (
        runtime_cfg.get("skip_startup_checks")
        if isinstance(runtime_cfg, dict)
        else None
    )
    debug_cfg = runtime_cfg.get("debug") if isinstance(runtime_cfg, dict) else None
    context_cfg = runtime_cfg.get("context") if isinstance(runtime_cfg, dict) else None
    risk_filter_cfg = (
        runtime_cfg.get("risk_vector_filter") if isinstance(runtime_cfg, dict) else None
    )
    max_findings_cfg = (
        runtime_cfg.get("max_findings") if isinstance(runtime_cfg, dict) else None
    )

    api_key_env = os.getenv("BITSIGHT_API_KEY")
    folder_env = os.getenv("BIRRE_SUBSCRIPTION_FOLDER")
    type_env = os.getenv("BIRRE_SUBSCRIPTION_TYPE")
    startup_skip_env = os.getenv("BIRRE_SKIP_STARTUP_CHECKS")
    debug_env = os.getenv("BIRRE_DEBUG") or os.getenv("DEBUG")
    context_env = os.getenv("BIRRE_CONTEXT")
    risk_filter_env = os.getenv(ENV_RISK_VECTOR_FILTER)
    max_findings_env = os.getenv(ENV_MAX_FINDINGS)

    api_key = api_key_arg or api_key_env or api_key_cfg
    subscription_folder = subscription_folder_arg or folder_env or folder_cfg
    subscription_type = subscription_type_arg or type_env or type_cfg

    normalized_context, context_invalid, context_requested = _normalize_context(
        context_arg or context_env or context_cfg
    )

    warnings = []
    if base_api_key_cfg not in (None, ""):
        warnings.append(
            "Avoid storing bitsight.api_key in config.toml; prefer config.local.toml, environment variables, or CLI overrides."
        )
    if context_invalid:
        warnings.append(
            f"Unknown context '{context_requested}' requested; defaulting to 'standard'"
        )

    skip_startup_checks = coerce_bool(startup_skip_cfg)
    skip_startup_checks = coerce_bool(startup_skip_env, default=skip_startup_checks)

    debug_enabled = coerce_bool(debug_cfg)
    debug_enabled = coerce_bool(debug_env, default=debug_enabled)
    debug_enabled = coerce_bool(debug_arg, default=debug_enabled)

    raw_filter = risk_vector_filter_arg or risk_filter_env or risk_filter_cfg
    raw_filter_str = str(raw_filter).strip() if raw_filter is not None else ""
    if raw_filter is not None and not raw_filter_str:
        warnings.append(
            "Empty risk_vector_filter override; falling back to default configuration"
        )
    risk_vector_filter = (
        raw_filter_str if raw_filter_str else DEFAULT_RISK_VECTOR_FILTER
    )

    raw_max_findings = (
        max_findings_arg
        if max_findings_arg is not None
        else max_findings_env
        if max_findings_env is not None
        else max_findings_cfg
    )
    try:
        max_findings = _coerce_positive_int(
            raw_max_findings,
            DEFAULT_MAX_FINDINGS,
        )
    except ValueError:
        warnings.append("Invalid max_findings override; using default configuration")
        max_findings = DEFAULT_MAX_FINDINGS

    if debug_enabled:
        os.environ["DEBUG"] = "true"
    else:
        os.environ.pop("DEBUG", None)

    os.environ["BIRRE_CONTEXT"] = normalized_context
    os.environ[ENV_RISK_VECTOR_FILTER] = risk_vector_filter
    os.environ[ENV_MAX_FINDINGS] = str(max_findings)

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
        "warnings": warnings,
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
        format_override
        or os.getenv(ENV_LOG_FORMAT)
        or config_section.get("format")
        or DEFAULT_LOG_FORMAT
    )

    file_value = file_override or os.getenv(ENV_LOG_FILE) or config_section.get("file")
    file_path = str(file_value).strip() if file_value else None
    if file_path == "":
        file_path = None

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
    api_key_arg: Optional[str] = None,
    config_path: str = "config.toml",
    subscription_folder_arg: Optional[str] = None,
    subscription_type_arg: Optional[str] = None,
    context_arg: Optional[str] = None,
    debug_arg: Optional[bool] = None,
    risk_vector_filter_arg: Optional[str] = None,
    max_findings_arg: Optional[int] = None,
    log_level_override: Optional[str] = None,
    log_format_override: Optional[str] = None,
    log_file_override: Optional[str] = None,
    log_max_bytes_override: Optional[int] = None,
    log_backup_count_override: Optional[int] = None,
) -> Tuple[Dict[str, Any], LoggingSettings]:
    runtime_settings = resolve_birre_settings(
        api_key_arg=api_key_arg,
        config_path=config_path,
        subscription_folder_arg=subscription_folder_arg,
        subscription_type_arg=subscription_type_arg,
        context_arg=context_arg,
        debug_arg=debug_arg,
        risk_vector_filter_arg=risk_vector_filter_arg,
        max_findings_arg=max_findings_arg,
    )
    logging_settings = resolve_logging_settings(
        config_path=config_path,
        level_override=log_level_override,
        format_override=log_format_override,
        file_override=log_file_override,
        max_bytes_override=log_max_bytes_override,
        backup_count_override=log_backup_count_override,
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
    "LoggingSettings",
    "LOG_FORMAT_TEXT",
    "LOG_FORMAT_JSON",
    "DEFAULT_RISK_VECTOR_FILTER",
    "DEFAULT_MAX_FINDINGS",
]
