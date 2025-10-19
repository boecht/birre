# BiRRe Implementation Status

## ⚠️ Latest Update: 2025-10-06 — Version 3.0.0 validated (offline + live suites passing)

### Major outstanding issues

- ⚠️ **CI automation pending**: Offline regression suite exists, but automated CI integration (including optional live smoke tests) still needs to be set up.

---

## Current Implementation Status

### ✅ FastMCP tool filtering (v1) — Stable

- Business server keeps only the v1 tools required for search, company detail, findings, folders, and subscription management; all other auto-generated tools are disabled at startup.
- `call_v1_tool` is attached to the business server for reuse by startup checks and future tooling.

### ✅ Risk manager context — Implemented

- `BIRRE_CONTEXT` / `--context` toggles between the standard (`company_search`, `get_company_rating`) and risk-manager (`company_search_interactive`, `manage_subscriptions`, `request_company`, plus rating/search) toolsets.
- `company_search_interactive` surfaces folder membership, subscription metadata, and employee counts via v1 helpers; guidance text instructs the calling LLM to obtain human confirmation rather than using `ctx.prompt`.
- `request_company` checks for existing BitSight company requests, prefers the v2 bulk endpoint (with folder targeting), and falls back to `createCompanyRequest` on schema failures—reflecting that v2 augments rather than replaces v1.
- `manage_subscriptions` wraps `manageSubscriptionsBulk` with dry-run previews and granular outcome summaries while reusing configured folder/type defaults.

### ✅ Startup checks — Implemented

- Offline checks ensure schemas exist, configuration is sane, and credentials are present before the server starts.
- Online checks (skippable via `--skip-startup-checks`, `BIRRE_SKIP_STARTUP_CHECKS`, or config) verify connectivity to BitSight, subscription folder/type presence, and quota state using the v1 FastMCP bridge.
- Combined offline/online results are emitted as structured JSON and abort startup on error.

### ⚠️ Testing infrastructure — Improved, needs expansion

- `uv run pytest -m 'not live'` exercises configuration layering, logging formatters, startup checks, subscription helpers, and both standard and risk-manager tools without network access.
- `uv run pytest -m live -rs` drives the FastMCP client against BitSight; both live suites pass with a configured `BITSIGHT_API_KEY`.
- Remaining gap: automate execution (CI) and determine how to provision BitSight credentials securely for optional live runs.

---

## Version Status

### Version 1.0 (MVP) — Functionally complete, needs hardening

- ✅ Company search via `companySearch`
- ✅ Company rating with trend analytics and ephemeral subscription cleanup
- ✅ Startup diagnostics executed before server launch
- ✅ Automated coverage in place for standard rating/search flow via offline unit tests

### Version 2.0 (Top Vulnerability Insights) — Functionally complete, needs tests

- `get_company_rating` now returns a `top_findings` block with relaxed filtering and web-appsec padding when severe/material findings are scarce
- Sorting logic elevates the highest-risk findings using severity, importance, and recency metrics
- Documentation and integrations should treat the enriched payload as part of the stable v2 adjunct contract (v2 augments v1 but never replaces it)

### Version 3.0 (Context Modes) — Functionally complete, needs hardening

- Context selection now respected via CLI (`--context`), environment (`BIRRE_CONTEXT`), and config defaults (`[roles].context`)
- `risk_manager` persona ships with `company_search_interactive`, `manage_subscriptions`, and `request_company`; each tool returns enriched metadata and guidance for LLM-driven human confirmation (no direct `ctx.prompt` usage)
- BitSight v2 bridge is auto-loaded for the request workflow (bulk path attempted, single-request fallback retained)
- Offline unit tests exercise dry-run and fallback behaviour; live FastMCP smoke tests now cover the company search + rating workflows.

### Version 4.0 (Caching Layer) — Not implemented

- Cache rating JSON plus recently generated PDFs for reuse across delivery channels

### Version 5.0 (Company Reports) — Not implemented

- Deliver BitSight reports via direct response, email, or configured file share (POSIX path or SharePoint)

### Version 6.0 (Multi-tenant service) — Not implemented

---

## Next Development Priorities (agreed)

1. Integrate the offline regression suite into CI and define a schedule for running live smoke tests.
2. Monitor BitSight v2 bulk usage and add complementary tooling where it provides net-new value.
3. Continue improving subscription lifecycle observability (error reporting, logging) for production readiness.

---

## Technical Notes

- FastMCP is pinned at `2.12.4` in `pyproject.toml` to prevent unexpected upstream API changes.
