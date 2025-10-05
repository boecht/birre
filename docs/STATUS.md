# BiRRe Implementation Status

## ⚠️ Latest Update: 2025-10-04 — Version 2.0 still not production ready

### Major outstanding issues

- ❌ **Automated tests absent**: No offline or live test suite protects the primary workflows. Rebuilding baseline coverage is the next agreed task.
- ⚠️ **BitSight v2 usage deferred**: The v2 FastMCP server can be preloaded (`BIRRE_ENABLE_V2=true`) but no shipping tool calls those endpoints yet.
- ⚠️ **Operational hardening**: Subscription lifecycle relies on the v1 `manageSubscriptionsBulk` endpoint with no automated regression coverage.

---

## Current Implementation Status

### ✅ FastMCP tool filtering (v1) — Stable

- Business server keeps only the v1 tools required for search, company detail, findings, folders, and subscription management; all other auto-generated tools are disabled at startup.
- `call_v1_tool` is attached to the business server for reuse by startup checks and future tooling.

### ⚠️ BitSight v2 coverage — Deferred

- `create_v2_api_server()` runs only when `BIRRE_ENABLE_V2` is truthy. The preloaded server is not referenced elsewhere, so runtime behaviour is unchanged today.
- Future features should introduce explicit v2 calling helpers instead of assuming automatic fallback.

### ✅ Startup checks — Implemented

- Offline checks ensure schemas exist, configuration is sane, and credentials are present before the server starts.
- Online checks (skippable via `--skip-startup-checks`, `BIRRE_SKIP_STARTUP_CHECKS`, or config) verify connectivity to BitSight, subscription folder/type presence, and quota state using the v1 FastMCP bridge.
- Combined offline/online results are emitted as structured JSON and abort startup on error.

### ❌ Testing infrastructure — Missing

- `pytest -m 'not live'` selects zero tests; the live suite was removed in September 2025 and has not been rebuilt.
- No CI-ready target exists because `fastmcp` must be installed via `uv` and BitSight credentials are required for any live testing.

---

## Version Status

### Version 1.0 (MVP) — Functionally complete, needs hardening

- ✅ Company search via `companySearch`
- ✅ Company rating with trend analytics and ephemeral subscription cleanup
- ✅ Startup diagnostics executed before server launch
- ⚠️ No automated tests to guard against regressions

### Version 2.0 (Top Vulnerability Insights) — Functionally complete, needs tests

- `get_company_rating` now returns a `top_findings` block with relaxed filtering and web-appsec padding when severe/material findings are scarce
- Sorting logic elevates the highest-risk findings using severity, importance, and recency metrics
- Documentation and integrations should treat the enriched payload as part of the stable v2 contract

### Version 3.0 (Context Modes) — Not implemented

- Specification updated: two contexts (`standard`, `risk_manager`) with distinct tool sets
- Implementation work outstanding: context selection, interactive search prompts, and batch subscription tooling

### Version 4.0 (Caching Layer) — Not implemented

- Cache rating JSON plus recently generated PDFs for reuse across delivery channels

### Version 5.0 (Company Reports) — Not implemented

- Deliver BitSight reports via direct response, email, or configured file share (POSIX path or SharePoint)

### Version 6.0 (Multi-tenant service) — Not implemented

---

## Next Development Priorities (agreed)

1. Rebuild a minimal offline/unit test suite around company search, rating assembly, and subscription helpers before any further feature work.
2. Prototype the forthcoming category risk ratings tool (planned for a future release) once tests exist.
3. Incrementally integrate BitSight v2 endpoints where they provide net-new data, using explicit helper functions to avoid hidden fallbacks.

---

## Technical Notes

- FastMCP is pinned at `2.12.4` in `pyproject.toml` to prevent unexpected upstream API changes.
- `BIRRE_ENABLE_V2` only preloads schemas; without new business logic nothing calls into v2.
- Startup checks depend on the attached `call_v1_tool` helper; changes to the FastMCP server wiring must preserve that attribute.

## MCP Client Snippet

Add the following entry to `@.mcp.json` to run the server via uv:

```json
    "birre": {
      "command": "uv",
      "args": [
        "run",
        "/home/vsc/Documents/Projects/birre/server.py"
      ],
      "env": {}
    }
```
