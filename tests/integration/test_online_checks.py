import os

import pytest

from birre import create_birre_server
from birre.application.startup import run_online_startup_checks
from birre.config.settings import RuntimeSettings, resolve_birre_settings
from birre.infrastructure.logging import get_logger

pytestmark = [pytest.mark.integration, pytest.mark.online]


@pytest.fixture(scope="module")
def online_runtime_settings() -> RuntimeSettings:
    """Load runtime settings using the configured BitSight API key."""

    api_key = os.getenv("BITSIGHT_API_KEY")
    if not api_key:
        pytest.skip("BITSIGHT_API_KEY not configured; skipping online tests")
    return resolve_birre_settings()


@pytest.fixture(scope="module")
def online_server(online_runtime_settings: RuntimeSettings):
    """Instantiate a BiRRe FastMCP server backed by live credentials."""

    logger = get_logger("birre.online.test")
    return create_birre_server(online_runtime_settings, logger=logger)


@pytest.mark.asyncio
async def test_run_online_startup_checks(
    online_runtime_settings: RuntimeSettings, online_server
) -> None:
    logger = get_logger("birre.online.startup")
    call_v1_tool = getattr(online_server, "call_v1_tool", None)
    assert call_v1_tool is not None, "BiRRe server does not expose call_v1_tool"

    result = await run_online_startup_checks(
        call_v1_tool=call_v1_tool,
        subscription_folder=online_runtime_settings.subscription_folder,
        subscription_type=online_runtime_settings.subscription_type,
        logger=logger,
        skip_startup_checks=False,
    )

    assert result.success is True
