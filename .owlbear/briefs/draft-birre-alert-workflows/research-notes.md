# BiRRe Alert Workflow Research Notes

## Verified Findings

- BiRRe is documented as a FastMCP server exposing curated business tools over hidden BitSight OpenAPI-generated tools.
- The current README describes `standard` and `risk_manager` use cases, with tools for company search, rating retrieval, interactive search, subscription management, and company requests.
- The architecture document explicitly supports business tools that orchestrate multiple internal API calls.
- `src/birre/config/settings.py` currently allows only `standard` and `risk_manager` contexts.
- `src/birre/application/server.py` currently registers the common rating tool for all contexts, adds standard search by default, and adds the richer risk-manager tools only for `risk_manager`.
- BitSight alert and finding endpoints exist in the local API endpoint docs, including alert listing/latest endpoints and company finding endpoints.
- BitSight v2 alert endpoints exist in the local API endpoint docs: `GET /alerts`, `GET /alerts/customer`, `GET /alerts/latest`, and `GET /alerts/{guid}/affected-companies`.
- The v2 `GET /alerts` spec supports `alert_date_gte`, `expand=details`, `limit`, `offset`, plus company, folder, type, severity, sort, and scope filters.
- The v2 alert response schema is paginated with `count`, `links.next`, `links.previous`, and `results`; each alert can include `guid`, `alert_type`, `alert_date`, `start_date`, `company_guid`, `company_name`, `folder_guid`, `folder_name`, `severity`, `trigger`, and type-specific `details`.
- BiRRe already has `create_v2_api_server` and `call_v2_openapi_tool`; the v2 helper currently lives in `integrations/bitsight/v1_bridge.py` rather than a separate v2 bridge module.
- Current server wiring creates a v2 API server only for the `risk_manager` context and allowlists `getCompanyRequests`, `createCompanyRequest`, and `createCompanyRequestBulk`, not alert tools.

## Candidate Implications

- Deterministic BitSight data retrieval, enrichment, and priority classification are likely a good fit for BiRRe's existing MCP/business-tool model.
- Durable ticket/documentation state, scheduling, retries across days, and Jira synchronization may need a separate storage/orchestration boundary unless BiRRe is intentionally expanded beyond MCP serving.
- A new context such as `alert_workflows` or `monitoring` may preserve the old interactive contexts while exposing automation-specific tools.
- The agent boundary should likely be text generation and judgment-heavy synthesis, while BiRRe owns repeatable data gathering, schema normalization, classification, and state-change proposals.
- A BiRRe-owned alert queue may reduce agent coordination burden, but it introduces durable state, idempotency, locking, replay, and failure semantics that the current MCP server does not appear to own.
- Direct Jira integration may be simpler than designing a generic ticket interface, but it would make BiRRe a multi-system workflow server rather than a BitSight-only server.
- The first useful slice can preserve the workflow promise with stable work-item IDs and deterministic ticket/action candidates before adding a durable queue.
- If Jira is the durable ticket record, BiRRe may still need minimal local correlation/audit state rather than full internal ticket storage.
- The first roadmap module is likely a v2 alert-triggered company intake and enrichment capability: fetch all alerts since a supplied date from `/v2/alerts`, expand details, traverse pagination, preserve source provenance, normalize results, and enrich each distinct company GUID through the existing v1 company-info path.
- The immediate prerequisite is likely v2 alert tool exposure/wiring, not creation of a brand-new v2 bridge from nothing.
- Company profile enrichment should remain explicitly v1-based unless v2 evidence shows equivalent fields; the user-provided `v1/companies/{guid}` sample supplies the ticket fields currently needed, and existing BiRRe code already calls `getCompany`.
- The module should preserve enough raw/source payload to avoid over-normalizing before later priority and Jira schema requirements are fully settled.
- Persistent cursor state is not required for the first module unless `alert_date_gte`, pagination ordering, or alert mutation semantics prove that stateless pulls can miss or duplicate operationally meaningful alerts.
- For Jira correlation, company GUID is the primary subject identity. Alert GUID should be retained as trigger/provenance and for deduplicating repeated alert-driven checks.
- The source of web-GUI rating-drop or finding-result details remains unresolved. The user has tested available alert endpoints in Stoplight and did not find the same information, so Phase 2 should treat this as a first-class research gap.

## Open Research Questions

- Which BitSight alert endpoint and payload shape corresponds to the user's configured alert trigger?
- Should `/v2/alerts/customer` stay out of the first module entirely, or be kept as a known follow-up variant after `/v2/alerts` works?
- What page size and pagination cap should the first alert-intake tool use to avoid accidental huge runs?
- Does `alert_date_gte` mean alert event date, creation/publication date, or last update date?
- Can v2 alerts change after first appearance, and if so does the endpoint expose an updated timestamp?
- What fields are required to map an alert to a company GUID, finding/risk vector, rating event, and due date?
- What alert identity should be retained for trigger provenance once company GUID is the primary Jira subject: alert GUID alone, or alert GUID plus alert type/date/trigger for extra stability?
- Where does the BitSight web GUI get rating-drop/finding-result information if the tested v1/v2 alert endpoints do not expose it?
- What is the intended documentation/ticket schema before Jira synchronization exists?
- Does ticket state need to be queryable via MCP tools, a CLI command, a local database/file store, or all three?
- What schedule/runtime will run the workflows: external scheduler calling MCP/CLI, a long-running service, or manual agent invocation?
- Which parts require LLM-authored text versus deterministic templates and rule-based enrichment?
- If BiRRe owns an internal alert queue, what guarantees are required: deduplication, retry count, per-item status, lock/lease, audit log, and resume-after-crash?
- If Jira is the ticket source of truth, what minimum local state still remains necessary for idempotency and mapping BitSight alert/finding IDs to Jira issue keys?
