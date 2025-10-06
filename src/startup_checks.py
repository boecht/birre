from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        self._logger.critical(message)


def run_offline_startup_checks(
    *,
    has_api_key: bool,
    subscription_folder: Optional[str],
    subscription_type: Optional[str],
    logger: logging.Logger,
) -> bool:
    if not has_api_key:
        logger.critical("offline.config.api_key: BITSIGHT_API_KEY is not set")
        return False

    logger.debug("offline.config.api_key: API key provided")

    for path in SCHEMA_PATHS:
        if not path.exists():
            logger.critical("offline.config.schema:%s: Schema file missing", path.name)
            return False

        try:
            with path.open("r", encoding="utf-8") as handle:
                json.load(handle)
        except Exception as exc:  # pragma: no cover - defensive
            logger.critical(
                "offline.config.schema:%s: Schema parse error: %s",
                path.name,
                exc,
            )
            return False

        logger.debug("offline.config.schema:%s: Schema parsed successfully", path.name)

    if subscription_folder:
        logger.debug(
            "offline.config.subscription_folder: Folder configured: %s",
            subscription_folder,
        )
    else:
        logger.warning(
            "offline.config.subscription_folder: BIRRE_SUBSCRIPTION_FOLDER not set"
        )

    if subscription_type:
        logger.debug(
            "offline.config.subscription_type: Subscription type configured: %s",
            subscription_type,
        )
    else:
        logger.warning(
            "offline.config.subscription_type: BIRRE_SUBSCRIPTION_TYPE not set"
        )

    return True


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
    logger: logging.Logger,
    skip_startup_checks: bool = False,
) -> bool:
    if skip_startup_checks:
        logger.warning(
            "online.startup_checks_skipped: Startup online checks skipped on request"
        )
        return True

    if call_v1_tool is None:
        logger.critical("online.api_connectivity: v1 call tool unavailable")
        return False

    ctx = _StartupCheckContext(logger)

    connectivity_issue = await _check_api_connectivity(call_v1_tool, ctx)
    if connectivity_issue is not None:
        logger.critical("online.api_connectivity: %s", connectivity_issue)
        return False

    logger.info("online.api_connectivity: Successfully called companySearch")

    if subscription_folder:
        folder_issue = await _check_subscription_folder(
            call_v1_tool, ctx, subscription_folder
        )
        if folder_issue is not None:
            logger.critical("online.subscription_folder_exists: %s", folder_issue)
            return False
        logger.info(
            "online.subscription_folder_exists: Folder '%s' verified via API",
            subscription_folder,
        )
    else:
        logger.error(
            "online.subscription_folder_exists: BIRRE_SUBSCRIPTION_FOLDER not set"
        )

    if subscription_type:
        quota_issue = await _check_subscription_quota(
            call_v1_tool, ctx, subscription_type
        )
        if quota_issue is not None:
            logger.critical("online.subscription_quota: %s", quota_issue)
            return False
        logger.info(
            "online.subscription_quota: Subscription '%s' has remaining licenses",
            subscription_type,
        )
    else:
        logger.error("online.subscription_quota: BIRRE_SUBSCRIPTION_TYPE not set")

    return True


__all__ = ["run_offline_startup_checks", "run_online_startup_checks"]
