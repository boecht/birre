from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any, NamedTuple

from fastmcp import Context

from birre.domain.common import CallV1Tool
from birre.infrastructure.logging import BoundLogger


class SubscriptionAttempt(NamedTuple):
    """Result of attempting to ensure a BitSight subscription."""

    success: bool
    created: bool
    already_subscribed: bool
    message: str | None = None


def _extract_guid_values(response: dict[str, Any], keys: Sequence[str]) -> list[str]:
    """Collect GUID strings from lists contained in the response."""

    guids: list[str] = []
    for key in keys:
        value = response.get(key)
        if not isinstance(value, list):
            continue

        for item in value:
            if isinstance(item, str):
                guids.append(item)
            elif isinstance(item, dict):
                guid_value = item.get("guid")
                if isinstance(guid_value, str):
                    guids.append(guid_value)

    return guids


def _build_subscription_payload(
    folder_name: str | None,
    subscription_type: str | None,
) -> dict[str, str | list[str]] | None:
    """Create the base payload for subscription actions when configured."""

    if not folder_name or not subscription_type:
        return None

    return {"folder": [folder_name], "type": subscription_type}


async def _log_bulk_response(
    ctx: Context, result: Any, action: str, *, debug_enabled: bool
) -> None:
    """Emit debug logging for bulk subscription responses when enabled."""

    if not debug_enabled:
        return

    if isinstance(result, dict):
        try:
            pretty = json.dumps(result, indent=2, sort_keys=True)
        except TypeError:
            pretty = str(result)
    else:
        pretty = str(result)
    await ctx.info(f"manageSubscriptionsBulk({action}) raw response: {pretty}")


async def _handle_bulk_errors(
    ctx: Context, errors: Any, guid: str
) -> SubscriptionAttempt | None:
    """Interpret the errors section from the bulk subscription response."""

    if not isinstance(errors, list):
        return None

    for error in errors:
        if not isinstance(error, dict):
            continue

        error_guid = error.get("guid")
        message = str(error.get("message") or "")
        normalized_message = message.lower()

        if error_guid and error_guid != guid:
            continue

        if "already exists" in normalized_message:
            await ctx.info(
                f"Company {guid} already subscribed according to bulk response"
            )
            return SubscriptionAttempt(True, False, True, message or None)

    if len(errors) > 0:
        message = f"FastMCP bulk subscription reported errors: {errors}"
        await ctx.error(message)
        return SubscriptionAttempt(False, False, False, message)

    return None


async def _interpret_manage_subscription_response(
    ctx: Context, result: Any, guid: str
) -> SubscriptionAttempt:
    """Translate the FastMCP bulk response into a SubscriptionAttempt."""

    if not isinstance(result, dict):
        message = (
            f"Unexpected response while managing subscription via FastMCP: {result}"
        )
        await ctx.error(message)
        return SubscriptionAttempt(False, False, False, message)

    added_guids = set(_extract_guid_values(result, ("added", "add")))
    if guid in added_guids:
        await ctx.info(
            f"Created temporary subscription for company {guid} using bulk API"
        )
        return SubscriptionAttempt(True, True, False)

    attempt = await _handle_bulk_errors(ctx, result.get("errors"), guid)
    if attempt is not None:
        return attempt

    modified_guids = set(_extract_guid_values(result, ("modified",)))
    if guid in modified_guids:
        await ctx.info(
            f"Subscription for company {guid} already active (reported as modified)"
        )
        return SubscriptionAttempt(True, False, True)

    await ctx.info(
        f"No add/modify/errors reported for {guid}; assuming already subscribed"
    )
    return SubscriptionAttempt(True, False, True)


async def create_ephemeral_subscription(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    guid: str,
    *,
    logger: BoundLogger,
    default_folder: str | None,
    subscription_type: str | None,
    debug_enabled: bool,
) -> SubscriptionAttempt:
    """Guarantee that the target company is subscribed before fetching data."""

    try:
        await ctx.info(f"Ensuring BitSight subscription for company: {guid}")

        subscription_base = _build_subscription_payload(
            default_folder, subscription_type
        )

        if not subscription_base:
            message = (
                "Subscription settings are missing. Configure subscription_folder and "
                "subscription_type via CLI or configuration."
            )
            await ctx.error(message)
            return SubscriptionAttempt(False, False, False, message)

        subscription_payload = {"add": [{**subscription_base, "guid": guid}]}

        result = await call_v1_tool(
            "manageSubscriptionsBulk", ctx, subscription_payload
        )

        await _log_bulk_response(ctx, result, "add", debug_enabled=debug_enabled)

        return await _interpret_manage_subscription_response(ctx, result, guid)

    except Exception as exc:  # pragma: no cover - defensive logging
        message = f"Failed to ensure subscription for {guid}: {exc}"
        await ctx.error(message)
        exc_info = exc if logging.getLogger().isEnabledFor(logging.DEBUG) else False
        logger.error(
            "subscription.ensure_failed",
            guid=guid,
            exc_info=exc_info,
        )
        return SubscriptionAttempt(False, False, False, message)


async def cleanup_ephemeral_subscription(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    guid: str,
    *,
    debug_enabled: bool,
) -> bool:
    """Revoke a temporary subscription once the data has been retrieved."""

    try:
        await ctx.info(f"Cleaning up ephemeral subscription for company: {guid}")

        delete_payload = {"delete": [{"guid": guid}]}
        result = await call_v1_tool("manageSubscriptionsBulk", ctx, delete_payload)

        await _log_bulk_response(ctx, result, "delete", debug_enabled=debug_enabled)

        if isinstance(result, dict) and result.get("errors"):
            await ctx.error(
                f"Failed to delete subscription via FastMCP: {result['errors']}"
            )
            return False

        await ctx.info("Issued FastMCP delete request for ephemeral subscription")
        return True

    except Exception as exc:  # pragma: no cover - defensive logging
        await ctx.error(f"Failed to cleanup ephemeral subscription for {guid}: {exc}")
        return False


__all__ = [
    "SubscriptionAttempt",
    "create_ephemeral_subscription",
    "cleanup_ephemeral_subscription",
]
