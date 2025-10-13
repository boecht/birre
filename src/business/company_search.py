from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastmcp import Context, FastMCP
from fastmcp.tools.tool import FunctionTool

from .helpers import CallV1Tool
from ..logging import log_search_event


COMPANY_SUMMARY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "guid": {"type": "string"},
        "name": {"type": "string"},
        "domain": {"type": "string"},
    },
    "required": ["guid", "name", "domain"],
    "additionalProperties": True,
}

COMPANY_SEARCH_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "error": {"type": "string"},
        "companies": {
            "type": "array",
            "items": COMPANY_SUMMARY_SCHEMA,
        },
        "count": {"type": "integer", "minimum": 0},
    },
    "required": [],
    "anyOf": [
        {"required": ["error"]},
        {"required": ["companies", "count"]},
    ],
    "additionalProperties": True,
}


def _extract_error(raw_result: Any) -> Optional[str]:
    if isinstance(raw_result, dict) and raw_result.get("error"):
        return f"BitSight API error: {raw_result['error']}"
    return None


def _extract_companies_data(raw_result: Any) -> List[Any]:
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


def _normalize_company(company: Dict[str, Any]) -> Dict[str, Any]:
    domain_candidates = (
        company.get("primary_domain"),
        company.get("display_url"),
        company.get("domain"),
        company.get("company_url"),
    )
    domain_value = next((value for value in domain_candidates if value), "")

    return {
        "guid": company.get("guid", ""),
        "name": company.get("name", ""),
        "domain": domain_value,
    }


def normalize_company_search_results(raw_result: Any) -> Dict[str, Any]:
    """Transform raw BitSight search results into the compact response shape."""

    error_message = _extract_error(raw_result)
    if error_message:
        return {
            "error": error_message,
            "companies": [],
            "count": 0,
        }

    companies: List[Dict[str, Any]] = [
        {
            "guid": str(company.get("guid") or ""),
            "name": str(company.get("name") or ""),
            "domain": str(
                next(
                    (
                        company.get("primary_domain"),
                        company.get("display_url"),
                        company.get("domain"),
                        company.get("company_url"),
                    ),
                    "",
                ) or "",
            ),
        }
        for company in _extract_companies_data(raw_result)
        if isinstance(company, dict)
    ]

    return {
        "companies": companies,
        "count": len(companies),
    }


def register_company_search_tool(
    business_server: FastMCP,
    call_v1_tool: CallV1Tool,
    *,
    logger: logging.Logger,
) -> FunctionTool:
    @business_server.tool(output_schema=COMPANY_SEARCH_OUTPUT_SCHEMA)
    async def company_search(
        ctx: Context, name: Optional[str] = None, domain: Optional[str] = None
    ) -> Dict[str, Any]:
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
          - domain: Primary domain if available; otherwise a representative URL (string, may be empty)
        - count: Number of companies returned (integer)

        Notes
        - At least one of name or domain must be provided. If both are provided, domain takes precedence.
        - Results are limited to the BitSight API's default page size (pagination not implemented).
        - Error contract: on failure returns {"error": str}.
        - Output is normalized for downstream use by other tools.

        Example
        >>> company_search(name="Github")
        {
          "companies": [
            {"guid": "e90b389b-0b7e-4722-9411-97d81c8e2bc6", "name": "GitHub, Inc.", "domain": "github.com"},
            {"guid": "a3b69f2e-ec1b-491e-adc9-e228cbd964a8", "name": "GitHub Blog", "domain": "github.blog"},
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
            response_payload = normalize_company_search_results(result)
            await ctx.info(
                f"Found {response_payload['count']} companies using FastMCP companySearch"
            )
            log_search_event(
                logger,
                "success",
                ctx=ctx,
                company_name=name,
                company_domain=domain,
                result_count=response_payload.get("count"),
            )
            return response_payload

        except Exception as exc:
            error_msg = f"FastMCP company search failed: {exc}"
            await ctx.error(error_msg)
            logger.error(error_msg, exc_info=True)
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

    return company_search  # type: ignore[return-value]


__all__ = ["register_company_search_tool"]
