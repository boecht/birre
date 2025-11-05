"""Offline and online startup checks for the BiRRe server."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from importlib import resources
from typing import Any, Protocol

from birre.infrastructure.errors import BirreError
from birre.infrastructure.logging import BoundLogger


class ToolLoggingContext(Protocol):
    """Subset of the FastMCP context API used by the startup checks."""

    async def info(self, message: str) -> None: ...  # pragma: no cover - protocol

    async def warning(self, message: str) -> None: ...  # pragma: no cover - protocol

    async def error(self, message: str) -> None: ...  # pragma: no cover - protocol


CallV1ToolFn = Callable[[str, ToolLoggingContext, dict[str, Any]], Awaitable[Any]]

SCHEMA_FILES: tuple[str, str] = (
    "bitsight.v1.schema.json",
    "bitsight.v2.schema.json",
)


class _StartupCheckContext:
    """Minimal context replicating FastMCP Context logging methods."""

    def __init__(self, logger: BoundLogger) -> None:
        self._logger = logger

    async def info(self, message: str) -> None:
        await asyncio.to_thread(self._logger.info, message)

    async def warning(self, message: str) -> None:
        await asyncio.to_thread(self._logger.warning, message)

    async def error(self, message: str) -> None:
        await asyncio.to_thread(self._logger.critical, message)


def run_offline_startup_checks(
    *,
    has_api_key: bool,
    subscription_folder: str | None,
    subscription_type: str | None,
    logger: BoundLogger,
) -> bool:
    if not has_api_key:
        logger.critical("offline.config.api_key.missing")
        return False

    logger.debug("offline.config.api_key.provided")

    for schema_name in SCHEMA_FILES:
        resource = resources.files("birre.resources") / "apis" / schema_name
        # Traversable protocol doesn't declare exists() in stub
        if not resource.exists():  # type: ignore[attr-defined]
            logger.critical(
                "offline.config.schema.missing",
                schema=schema_name,
            )
            return False

        try:
            with resources.as_file(resource) as path:
                with path.open("r", encoding="utf-8") as handle:
                    json.load(handle)
        except Exception as exc:  # pragma: no cover - defensive
            logger.critical(
                "offline.config.schema.parse_error",
                schema=schema_name,
                error=str(exc),
            )
            return False

        logger.debug(
            "offline.config.schema.parsed",
            schema=schema_name,
        )

    if subscription_folder:
        logger.debug(
            "offline.config.subscription_folder.configured",
            subscription_folder=subscription_folder,
        )
    else:
        logger.warning("offline.config.subscription_folder.missing")

    if subscription_type:
        logger.debug(
            "offline.config.subscription_type.configured",
            subscription_type=subscription_type,
        )
    else:
        logger.warning("offline.config.subscription_type.missing")

    return True


async def _check_api_connectivity(
    call_v1_tool: CallV1ToolFn, ctx: ToolLoggingContext
) -> str | None:
    try:
        await call_v1_tool("companySearch", ctx, {"name": "bitsight", "limit": 1})
        return None
    except BirreError:
        raise
    except Exception as exc:  # pragma: no cover - network failure
        return f"{exc.__class__.__name__}: {exc}"


async def _check_subscription_folder(
    call_v1_tool: CallV1ToolFn, ctx: ToolLoggingContext, folder: str
) -> str | None:
    try:
        raw = await call_v1_tool("getFolders", ctx, {})
    except BirreError:
        raise
    except Exception as exc:
        return f"Failed to query folders: {exc.__class__.__name__}: {exc}"

    folders: list[str] = []
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
    call_v1_tool: CallV1ToolFn,
    ctx: ToolLoggingContext,
    subscription_type: str,
) -> str | None:
    try:
        raw = await call_v1_tool("getCompanySubscriptions", ctx, {})
    except BirreError:
        raise
    except Exception as exc:
        return f"Failed to query subscriptions: {exc.__class__.__name__}: {exc}"

    if not isinstance(raw, dict):
        return "No subscription data returned"

    available_types = [key for key in raw if isinstance(key, str)]
    details = raw.get(subscription_type)
    raw = None  # free response

    if not isinstance(details, dict):
        if available_types:
            return (
                f"Subscription type '{subscription_type}' not found; available types:"
                f" {', '.join(sorted(available_types))}"
            )
        return "No subscription data returned"

    remaining = details.get("remaining")
    if not isinstance(remaining, int):
        return f"Subscription '{subscription_type}' remaining value unexpected: {remaining!r}"
    if remaining <= 0:
        return f"Subscription '{subscription_type}' has no remaining licenses"
    return None


async def _validate_subscription_folder(
    call_v1_tool: CallV1ToolFn,
    ctx: ToolLoggingContext,
    subscription_folder: str | None,
    logger: BoundLogger,
) -> bool:
    if not subscription_folder:
        logger.warning(
            "online.subscription_folder_exists.skipped",
            reason="BIRRE_SUBSCRIPTION_FOLDER not set",
        )
        return True

    folder_issue = await _check_subscription_folder(call_v1_tool, ctx, subscription_folder)
    if folder_issue is not None:
        logger.critical(
            "online.subscription_folder_exists.failed",
            issue=folder_issue,
        )
        return False

    logger.info(
        "online.subscription_folder_exists.verified",
        subscription_folder=subscription_folder,
    )
    return True


async def _validate_subscription_quota(
    call_v1_tool: CallV1ToolFn,
    ctx: ToolLoggingContext,
    subscription_type: str | None,
    logger: BoundLogger,
) -> bool:
    if not subscription_type:
        logger.warning(
            "online.subscription_quota.skipped",
            reason="BIRRE_SUBSCRIPTION_TYPE not set",
        )
        return True

    quota_issue = await _check_subscription_quota(call_v1_tool, ctx, subscription_type)
    if quota_issue is not None:
        logger.critical(
            "online.subscription_quota.failed",
            issue=quota_issue,
        )
        return False

    logger.info(
        "online.subscription_quota.verified",
        subscription_type=subscription_type,
    )
    return True


async def run_online_startup_checks(
    *,
    call_v1_tool: CallV1ToolFn,
    subscription_folder: str | None,
    subscription_type: str | None,
    logger: BoundLogger,
    skip_startup_checks: bool = False,
) -> bool:
    if skip_startup_checks:
        logger.warning(
            "online.startup_checks.skipped",
            reason="skip_startup_checks flag set",
        )
        return True

    if call_v1_tool is None:
        logger.critical("online.api_connectivity.unavailable")
        return False

    ctx = _StartupCheckContext(logger)

    connectivity_issue = await _check_api_connectivity(call_v1_tool, ctx)
    if connectivity_issue is not None:
        logger.critical(
            "online.api_connectivity.failed",
            issue=connectivity_issue,
        )
        return False

    logger.info("online.api_connectivity.success")

    if not await _validate_subscription_folder(call_v1_tool, ctx, subscription_folder, logger):
        return False

    if not await _validate_subscription_quota(call_v1_tool, ctx, subscription_type, logger):
        return False

    return True


__all__ = ["run_offline_startup_checks", "run_online_startup_checks"]
