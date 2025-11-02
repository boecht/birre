from __future__ import annotations

import asyncio

import pytest

import birre.domain.company_rating.service as svc


class _Ctx:
    async def info(self, *_, **__):  # noqa: ANN001
        await asyncio.sleep(0)

    async def warning(self, *_, **__):  # noqa: ANN001
        await asyncio.sleep(0)

    async def error(self, *_, **__):  # noqa: ANN001
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_fetch_company_profile_dict_validates_shape() -> None:
    # Non-dict result should raise
    async def _call(tool: str, ctx, params):  # noqa: ANN001
        await asyncio.sleep(0)
        return 123

    with pytest.raises(ValueError):
        await svc._fetch_company_profile_dict(_call, _Ctx(), "g")


@pytest.mark.asyncio
async def test_retrieve_top_findings_payload_handles_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(*args, **kwargs):  # noqa: ANN001
        raise RuntimeError("fail")

    monkeypatch.setattr(svc, "_assemble_top_findings_section", _boom)
    out = await svc._retrieve_top_findings_payload(
        lambda *a, **k: None,
        _Ctx(),
        "g",
        "rv",
        5,
        debug_enabled=False,
    )  # type: ignore[arg-type]
    assert out.policy.profile == "unavailable" and out.count == 0


@pytest.mark.asyncio
async def test_build_rating_payload_success(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub company profile and findings
    async def _company(tool: str, ctx, params):  # noqa: ANN001
        await asyncio.sleep(0)
        return {
            "name": "Example Corp",
            "primary_domain": "example.com",
            "current_rating": 740,
            "ratings": [
                {"rating_date": "2025-10-01", "rating": 700},
                {"rating_date": "2025-10-15", "rating": 720},
            ],
        }

    async def _findings(*args, **kwargs):  # noqa: ANN001
        await asyncio.sleep(0)
        return svc.TopFindings.model_validate(
            {
                "policy": {
                    "severity_floor": "material",
                    "supplements": [],
                    "max_items": 3,
                    "profile": "strict",
                },
                "count": 0,
                "findings": [],
            }
        )

    # Avoid touching real logging
    monkeypatch.setattr(svc, "_retrieve_top_findings_payload", _findings)
    import birre.infrastructure.logging as bil

    monkeypatch.setattr(bil, "log_rating_event", lambda *a, **k: None)

    class _Logger:
        def bind(self, **kwargs):  # structlog-like interface
            return self

        def info(self, *args, **kwargs):  # noqa: ANN001
            return None

        def error(self, *args, **kwargs):  # noqa: ANN001
            return None

        def log(self, level, message, **kwargs):  # noqa: ANN001
            return None

    logger = _Logger()
    out = await svc._build_rating_payload(
        _company,
        _Ctx(),
        "guid-1",
        "rv",
        5,
        logger,
        debug_enabled=False,
    )
    assert out.name == "Example Corp" and out.current_rating and out.legend


# Note: error handling for rating endpoint is covered via _retrieve_top_findings_payload
# and by higher-level tool wrappers; _build_rating_payload intentionally propagates
# unexpected exceptions for the caller to handle.
