"""Company search tool implementation for BiRRe."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from fastmcp import Context, FastMCP
from fastmcp.tools.tool import FunctionTool
from pydantic import BaseModel, Field, model_validator

from birre.domain.common import CallV1Tool
from birre.infrastructure.errors import BirreError
from birre.infrastructure.logging import BoundLogger, log_search_event


class CompanySummary(BaseModel):
    guid: str = Field(default="", description="BitSight company GUID")
    name: str = Field(default="", description="Display name for the company")
    domain: str = Field(default="", description="Primary domain or representative URL")

    @model_validator(mode="before")
    @classmethod
    def _normalize_input(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {"guid": "", "name": "", "domain": ""}

        def _first_present(candidates: Iterable[Any]) -> str:
            for candidate in candidates:
                if candidate:
                    return str(candidate)
            return ""

        domain_value = _first_present(
            (
                value.get("primary_domain"),
                value.get("display_url"),
                value.get("domain"),
                value.get("company_url"),
            )
        )

        return {
            "guid": str(value.get("guid") or ""),
            "name": str(value.get("name") or ""),
            "domain": domain_value,
        }


class CompanySearchResponse(BaseModel):
    error: str | None = Field(
        default=None, description="Error message if the search failed"
    )
    companies: list[CompanySummary] = Field(default_factory=list)
    count: int = Field(default=0, ge=0)

    @staticmethod
    def _extract_error(raw_result: Any) -> str | None:
        if isinstance(raw_result, dict) and raw_result.get("error"):
            return f"BitSight API error: {raw_result['error']}"
        return None

    @staticmethod
    def _extract_companies(raw_result: Any) -> list[Any]:
        if isinstance(raw_result, dict):
            for key in ("results", "companies"):
                if key in raw_result:
                    return raw_result.get(key) or []
            if raw_result.get("guid"):
                return [raw_result]
            return []
        if isinstance(raw_result, list):
            return raw_result
        return []

    @classmethod
    def from_raw(cls, raw_result: Any) -> CompanySearchResponse:
        error_message = cls._extract_error(raw_result)
        if error_message:
            return cls(error=error_message, companies=[], count=0)

        company_models = [
            CompanySummary.model_validate(candidate)
            for candidate in cls._extract_companies(raw_result)
            if isinstance(candidate, dict)
        ]

        return cls(companies=company_models, count=len(company_models))

    def to_payload(self) -> dict[str, Any]:
        if self.error:
            return {"error": self.error}
        data = self.model_dump(exclude_unset=True)
        data.pop("error", None)
        return data


COMPANY_SEARCH_OUTPUT_SCHEMA: dict[str, Any] = CompanySearchResponse.model_json_schema()


def normalize_company_search_results(raw_result: Any) -> dict[str, Any]:
    """Transform raw BitSight search results into the compact response shape."""

    return CompanySearchResponse.from_raw(raw_result).to_payload()


def register_company_search_tool(
    business_server: FastMCP,
    call_v1_tool: CallV1Tool,
    *,
    logger: BoundLogger,
) -> FunctionTool:
    @business_server.tool(output_schema=COMPANY_SEARCH_OUTPUT_SCHEMA)
    async def company_search(
        ctx: Context, name: str | None = None, domain: str | None = None
    ) -> dict[str, Any]:
        """Search on BitSight for companies by name or domain.

        Parameters
        - name: Optional company name (partial matches allowed by API)
        - domain: Optional primary domain (exact match preferred)

        Returns
        - {"companies": [{"guid": str,"name": str,"domain": str}, ...], "count": int}

        Output semantics
        - companies: List of company summaries. Each item contains:
        - guid: BitSight company GUID (string)
        - name: Display name (string)
        - domain: Primary domain if available; otherwise a representative
            URL (string, may be empty)
        - count: Number of companies returned (integer)

        Notes
        - At least one of name or domain must be provided. If both are
        provided, domain takes precedence.
        - Results are limited to the BitSight API's default page size (pagination not implemented).
        - Error contract: on failure returns {"error": str}.
        - Output is normalized for downstream use by other tools.

        Example
        >>> company_search(name="Github")
        {
        "companies": [
            {
                "guid": "e90b389b-0b7e-4722-9411-97d81c8e2bc6",
                "name": "GitHub, Inc.", "domain": "github.com"
            },
            {
                "guid": "a3b69f2e-ec1b-491e-adc9-e228cbd964a8",
                "name": "GitHub Blog", "domain": "github.blog"
            },
            ...
        ],
        "count": 5
        }
        Select the GUID for "GitHub, Inc." to use with get_company_rating.
        """
        if not name and not domain:
            return {
                "error": "At least one of 'name' or 'domain' must be provided",
            }

        search_term = domain if domain else (name or "")
        await ctx.info(f"Starting company search for: {search_term}")
        log_search_event(
            logger,
            "start",
            ctx=ctx,
            company_name=name,
            company_domain=domain,
        )

        try:
            params = {"name": name, "domain": domain}
            result = await call_v1_tool("companySearch", ctx, params)
            response_payload = CompanySearchResponse.from_raw(result).to_payload()
            if "error" in response_payload:
                error_message = response_payload["error"]
                await ctx.warning(
                    f"FastMCP companySearch returned an error response: {error_message}"
                )
                log_search_event(
                    logger,
                    "failure",
                    ctx=ctx,
                    company_name=name,
                    company_domain=domain,
                    error=error_message,
                )
                return response_payload

            result_count = response_payload.get("count", 0)
            await ctx.info(
                f"Found {result_count} companies using FastMCP companySearch"
            )
            log_search_event(
                logger,
                "success",
                ctx=ctx,
                company_name=name,
                company_domain=domain,
                result_count=result_count,
            )
            return response_payload

        except BirreError as exc:
            error_msg = exc.user_message
            await ctx.error(error_msg)
            log_search_event(
                logger,
                "failure",
                ctx=ctx,
                company_name=name,
                company_domain=domain,
                error=error_msg,
            )
            return {"error": error_msg}

        except Exception as exc:
            error_msg = f"FastMCP company search failed: {exc}"
            await ctx.error(error_msg)
            exc_info = exc if logging.getLogger().isEnabledFor(logging.DEBUG) else False
            logger.error(
                "company_search.error",
                error=str(exc),
                exc_info=exc_info,
            )
            log_search_event(
                logger,
                "failure",
                ctx=ctx,
                company_name=name,
                company_domain=domain,
                error=str(exc),
            )
            return {
                "error": error_msg,
            }

    return company_search


__all__ = ["register_company_search_tool"]
