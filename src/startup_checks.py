from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logging import get_logger, log_event

LOGGER = get_logger(__name__)

SCHEMA_PATHS = (
    Path("apis/bitsight.v1.schema.json"),
    Path("apis/bitsight.v2.schema.json"),
)


class _StartupCheckContext:
    """Minimal context replicating FastMCP Context logging methods."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    async def info(self, message: str) -> None:
        self._logger.info(message)

    async def warning(self, message: str) -> None:
        self._logger.warning(message)

    async def error(self, message: str) -> None:
        self._logger.error(message)


def run_offline_startup_checks(
    *,
    api_key_present: bool,
    subscription_folder: Optional[str],
    subscription_type: Optional[str],
    logger: Optional[logging.Logger] = None,
) -> Dict[str, Any]:
    check_logger = logger or LOGGER
    checks: List[Dict[str, Any]] = []

    def record(name: str, status: str, details: str) -> None:
        checks.append({"check": name, "status": status, "details": details})

    if api_key_present:
        record("config.api_key", "ok", "API key provided")
    else:
        record("config.api_key", "error", "BITSIGHT_API_KEY is not set")

    for path in SCHEMA_PATHS:
        if not path.exists():
            record(f"config.schema:{path.name}", "error", "Schema file missing")
        else:
            try:
                with path.open("r", encoding="utf-8") as handle:
                    json.load(handle)
                record(f"config.schema:{path.name}", "ok", "Schema parsed successfully")
            except Exception as exc:  # pragma: no cover - defensive
                record(
                    f"config.schema:{path.name}", "error", f"Schema parse error: {exc}"
                )

    if subscription_folder:
        record(
            "config.subscription_folder",
            "ok",
            f"Folder configured: {subscription_folder}",
        )
    else:
        record(
            "config.subscription_folder", "warning", "BIRRE_SUBSCRIPTION_FOLDER not set"
        )

    if subscription_type:
        record(
            "config.subscription_type",
            "ok",
            f"Subscription type configured: {subscription_type}",
        )
    else:
        record("config.subscription_type", "warning", "BIRRE_SUBSCRIPTION_TYPE not set")

    summary = {
        "ok": sum(1 for c in checks if c["status"] == "ok"),
        "warning": sum(1 for c in checks if c["status"] == "warning"),
        "error": sum(1 for c in checks if c["status"] == "error"),
    }

    log_event(check_logger, "startup_checks.offline", summary=summary, checks=checks)

    return {"summary": summary, "checks": checks}


async def _check_api_connectivity(call_v1_tool, ctx: Any) -> Optional[str]:
    try:
        await call_v1_tool("companySearch", ctx, {"name": "bitsight", "limit": 1})
        return None
    except Exception as exc:  # pragma: no cover - network failure
        return str(exc)


async def _check_subscription_folder(
    call_v1_tool, ctx: Any, folder: str
) -> Optional[str]:
    try:
        raw = await call_v1_tool("getFolders", ctx, {})
    except Exception as exc:
        return f"Failed to query folders: {exc}"

    folders: List[str] = []
    if isinstance(raw, list):
        iterable = raw
    elif isinstance(raw, dict):
        iterable = raw.get("results") or raw.get("folders") or []
    else:
        iterable = []

    for entry in iterable:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            folders.append(entry["name"])

    raw = None  # free response

    if not folders:
        return "No folders returned from BitSight"
    if folder in folders:
        return None
    return f"Folder '{folder}' not found; available: {', '.join(sorted(folders))}"


async def _check_subscription_quota(
    call_v1_tool, ctx: Any, subscription_type: str
) -> Optional[str]:
    try:
        raw = await call_v1_tool("getCompanySubscriptions", ctx, {})
    except Exception as exc:
        return f"Failed to query subscriptions: {exc}"

    details: Optional[Dict[str, Any]] = None
    available_types: List[str] = []
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(key, str):
                available_types.append(key)
                if key == subscription_type and isinstance(value, dict):
                    details = value

    raw = None  # free response

    if details is None:
        if available_types:
            return (
                f"Subscription type '{subscription_type}' not found; available types:"
                f" {', '.join(sorted(available_types))}"
            )
        return "No subscription data returned"

    remaining = details.get("remaining")
    if isinstance(remaining, int):
        if remaining > 0:
            return None
        return f"Subscription '{subscription_type}' has no remaining licenses"
    return f"Subscription '{subscription_type}' returned unexpected remaining value: {remaining!r}"


async def run_online_startup_checks(
    *,
    call_v1_tool,
    subscription_folder: Optional[str],
    subscription_type: Optional[str],
    logger: Optional[logging.Logger] = None,
    skip_startup_checks: bool = False,
) -> Dict[str, Any]:
    diag_logger = logger or LOGGER
    checks: List[Dict[str, Any]] = []

    def record(name: str, status: str, details: str) -> None:
        checks.append({"check": name, "status": status, "details": details})

    if skip_startup_checks:
        record(
            "startup_checks_skipped",
            "warning",
            "Startup online checks skipped on request",
        )
        summary = {
            "ok": sum(1 for c in checks if c["status"] == "ok"),
            "warning": sum(1 for c in checks if c["status"] == "warning"),
            "error": sum(1 for c in checks if c["status"] == "error"),
        }
        log_event(diag_logger, "startup_checks.online", summary=summary, checks=checks)
        return {"summary": summary, "checks": checks}

    if call_v1_tool is None:
        record("api_connectivity", "error", "v1 call tool unavailable")
    else:
        ctx = _StartupCheckContext(diag_logger)

        connectivity_issue = await _check_api_connectivity(call_v1_tool, ctx)
        if connectivity_issue is None:
            record("api_connectivity", "ok", "Successfully called companySearch")
        else:
            record("api_connectivity", "error", connectivity_issue)

        if subscription_folder:
            folder_issue = await _check_subscription_folder(
                call_v1_tool, ctx, subscription_folder
            )
            if folder_issue is None:
                record(
                    "subscription_folder_exists",
                    "ok",
                    f"Folder '{subscription_folder}' verified via API",
                )
            else:
                record("subscription_folder_exists", "error", folder_issue)
        else:
            record(
                "subscription_folder_exists",
                "warning",
                "BIRRE_SUBSCRIPTION_FOLDER not set",
            )

        if subscription_type:
            quota_issue = await _check_subscription_quota(
                call_v1_tool, ctx, subscription_type
            )
            if quota_issue is None:
                record(
                    "subscription_quota",
                    "ok",
                    f"Subscription '{subscription_type}' has remaining licenses",
                )
            else:
                record("subscription_quota", "error", quota_issue)
        else:
            record("subscription_quota", "warning", "BIRRE_SUBSCRIPTION_TYPE not set")

    summary = {
        "ok": sum(1 for c in checks if c["status"] == "ok"),
        "warning": sum(1 for c in checks if c["status"] == "warning"),
        "error": sum(1 for c in checks if c["status"] == "error"),
    }

    log_event(diag_logger, "startup_checks.online", summary=summary, checks=checks)

    return {"summary": summary, "checks": checks}


__all__ = ["run_offline_startup_checks", "run_online_startup_checks"]
