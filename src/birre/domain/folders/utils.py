"""Folder resolution and creation helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastmcp import Context

from birre.infrastructure.logging import BoundLogger, log_event

CallV1Tool = Any


@dataclass(frozen=True)
class FolderResolutionResult:
    guid: str | None
    created: bool
    error: str | None = None


async def _fetch_folders(
    call_v1_tool: CallV1Tool, ctx: Context
) -> list[dict[str, Any]]:
    raw = await call_v1_tool("getFolders", ctx, {})
    iterable: list[Any]
    if isinstance(raw, list):
        iterable = raw
    elif isinstance(raw, dict):
        iterable = raw.get("results") or raw.get("folders") or []
    else:
        iterable = []

    records: list[dict[str, Any]] = []
    for entry in iterable:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        guid = entry.get("guid")
        if isinstance(name, str) and isinstance(guid, str):
            records.append({"name": name, "guid": guid})
    return records


async def _try_fetch_folders(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    *,
    logger: BoundLogger,
    folder_name: str,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    try:
        return await _fetch_folders(call_v1_tool, ctx), None
    except Exception as exc:  # pragma: no cover - network path
        log_event(
            logger,
            "folder.lookup_failed",
            level=logging.WARNING,
            folder=folder_name,
            error=str(exc),
        )
        return None, f"Failed to fetch folders: {exc}"


def _find_folder_guid(
    folders: list[dict[str, Any]],
    folder_name: str,
) -> str | None:
    for entry in folders:
        name = entry.get("name")
        guid = entry.get("guid")
        if name == folder_name and isinstance(guid, str) and guid:
            return guid
    return None


def _format_missing_folder_error(
    folders: list[dict[str, Any]],
    folder_name: str,
) -> str:
    available_names: list[str] = []
    for entry in folders:
        name = entry.get("name")
        if isinstance(name, str):
            available_names.append(name)
    available = ", ".join(sorted(available_names)) or "none"
    return f"Folder '{folder_name}' not found; available: {available}"


def _extract_guid(payload: Any) -> str | None:
    if isinstance(payload, dict):
        guid_value = payload.get("guid") or payload.get("folder_guid")
        if isinstance(guid_value, str) and guid_value:
            return guid_value
    return None


async def _lookup_guid_by_name(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    folder_name: str,
) -> str | None:
    try:
        folders = await _fetch_folders(call_v1_tool, ctx)
    except Exception:  # pragma: no cover - best-effort fallback
        return None
    return _find_folder_guid(folders, folder_name)


async def _create_folder_and_get_guid(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    *,
    logger: BoundLogger,
    folder_name: str,
    tool_name: str,
) -> tuple[str | None, str | None]:
    description = (
        "created by BiRRe during "
        f"{tool_name} call on {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    body = {"name": folder_name, "description": description}
    try:
        created_payload = await call_v1_tool("createFolder", ctx, body)
    except Exception as exc:  # pragma: no cover - network path
        log_event(
            logger,
            "folder.create_failed",
            level=logging.WARNING,
            folder=folder_name,
            error=str(exc),
        )
        return None, f"Unable to create folder '{folder_name}': {exc}"

    created_guid = _extract_guid(created_payload)
    if created_guid:
        return created_guid, None

    fallback_guid = await _lookup_guid_by_name(call_v1_tool, ctx, folder_name)
    if fallback_guid:
        return fallback_guid, None

    return None, "Folder creation response missing GUID"


async def resolve_or_create_folder(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    *,
    logger: BoundLogger,
    folder_name: str | None,
    tool_name: str,
    allow_create: bool,
) -> FolderResolutionResult:
    if not folder_name:
        return FolderResolutionResult(guid=None, created=False, error=None)

    folders, fetch_error = await _try_fetch_folders(
        call_v1_tool,
        ctx,
        logger=logger,
        folder_name=folder_name,
    )
    if fetch_error or folders is None:
        return FolderResolutionResult(guid=None, created=False, error=fetch_error)

    existing_guid = _find_folder_guid(folders, folder_name)
    if existing_guid:
        return FolderResolutionResult(guid=existing_guid, created=False, error=None)

    if not allow_create:
        return FolderResolutionResult(
            guid=None,
            created=False,
            error=_format_missing_folder_error(folders, folder_name),
        )

    created_guid, creation_error = await _create_folder_and_get_guid(
        call_v1_tool,
        ctx,
        logger=logger,
        folder_name=folder_name,
        tool_name=tool_name,
    )
    if creation_error or not created_guid:
        return FolderResolutionResult(guid=None, created=False, error=creation_error)

    log_event(
        logger,
        "folder.created",
        folder=folder_name,
        folder_guid=created_guid,
        tool=tool_name,
    )
    return FolderResolutionResult(guid=created_guid, created=True, error=None)


__all__ = [
    "FolderResolutionResult",
    "resolve_or_create_folder",
]
