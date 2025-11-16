"""Offline and online startup checks for the BiRRe server."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
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


@dataclass(frozen=True)
class OnlineStartupResult:
    success: bool
    subscription_folder_guid: str | None = None


class _StartupCheckContext:
    """Minimal context replicating FastMCP Context logging methods."""

    def __init__(self, logger: BoundLogger) -> None:
        self._logger = logger
        self.subscription_folder_guid: str | None = None

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
        try:
            with resources.as_file(resource) as path:
                with path.open("r", encoding="utf-8") as handle:
                    json.load(handle)
        except FileNotFoundError:
            logger.critical(
                "offline.config.schema.missing",
                schema=schema_name,
            )
            return False
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


def _folder_entries_from_response(raw: Any) -> Any:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return raw.get("results") or raw.get("folders") or []
    return []


def _collect_folder_catalog(entries: Any) -> tuple[list[str], dict[str, str]]:
    folders: list[str] = []
    guid_lookup: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        folders.append(name)
        guid_value = entry.get("guid")
        if isinstance(guid_value, str) and guid_value:
            guid_lookup[name] = guid_value
    return folders, guid_lookup


async def _check_subscription_folder(
    call_v1_tool: CallV1ToolFn, ctx: ToolLoggingContext, folder: str
) -> tuple[str | None, str | None]:
    try:
        raw = await call_v1_tool("getFolders", ctx, {})
    except BirreError:
        raise
    except Exception as exc:
        return f"Failed to query folders: {exc.__class__.__name__}: {exc}", None

    iterable = _folder_entries_from_response(raw)
    folders, guid_lookup = _collect_folder_catalog(iterable)

    raw = None  # free response

    if not folders:
        return "No folders returned from BitSight", None
    if folder in folders:
        return None, guid_lookup.get(folder)
    return (
        f"Folder '{folder}' not found; available: {', '.join(sorted(folders))}",
        None,
    )


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
) -> tuple[bool, str | None]:
    if not subscription_folder:
        logger.warning(
            "online.subscription_folder_exists.skipped",
            reason="BIRRE_SUBSCRIPTION_FOLDER not set",
        )
        return True, None

    folder_issue, folder_guid = await _check_subscription_folder(
        call_v1_tool, ctx, subscription_folder
    )
    if folder_issue is not None:
        logger.critical(
            "online.subscription_folder_exists.failed",
            issue=folder_issue,
        )
        return False, None

    logger.info(
        "online.subscription_folder_exists.verified",
        subscription_folder=subscription_folder,
    )
    return True, folder_guid


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


async def _ensure_api_connectivity(
    call_v1_tool: CallV1ToolFn | None,
    ctx: ToolLoggingContext,
    logger: BoundLogger,
) -> bool:
    if call_v1_tool is None:
        logger.critical("online.api_connectivity.unavailable")
        return False

    connectivity_issue = await _check_api_connectivity(call_v1_tool, ctx)
    if connectivity_issue is not None:
        logger.critical(
            "online.api_connectivity.failed",
            issue=connectivity_issue,
        )
        return False

    logger.info("online.api_connectivity.success")
    return True


async def run_online_startup_checks(
    *,
    call_v1_tool: CallV1ToolFn,
    subscription_folder: str | None,
    subscription_type: str | None,
    logger: BoundLogger,
    skip_startup_checks: bool = False,
) -> OnlineStartupResult:
    if skip_startup_checks:
        logger.warning(
            "online.startup_checks.skipped",
            reason="skip_startup_checks flag set",
        )
        return OnlineStartupResult(success=True)

    ctx = _StartupCheckContext(logger)

    success, folder_guid = await _perform_online_validations(
        call_v1_tool,
        ctx,
        logger,
        subscription_folder,
        subscription_type,
    )
    if not success:
        return OnlineStartupResult(success=False)

    ctx.subscription_folder_guid = folder_guid
    return OnlineStartupResult(success=True, subscription_folder_guid=folder_guid)


async def _perform_online_validations(
    call_v1_tool: CallV1ToolFn,
    ctx: _StartupCheckContext,
    logger: BoundLogger,
    subscription_folder: str | None,
    subscription_type: str | None,
) -> tuple[bool, str | None]:
    if not await _ensure_api_connectivity(call_v1_tool, ctx, logger):
        return False, None

    folder_ok, folder_guid = await _validate_subscription_folder(
        call_v1_tool, ctx, subscription_folder, logger
    )
    if not folder_ok:
        return False, None

    if not await _validate_subscription_quota(
        call_v1_tool, ctx, subscription_type, logger
    ):
        return False, folder_guid

    return True, folder_guid


__all__ = ["run_offline_startup_checks", "run_online_startup_checks"]
