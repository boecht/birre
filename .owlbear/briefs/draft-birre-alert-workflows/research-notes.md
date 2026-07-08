# BiRRe Alert Workflow Research Notes

## Verified Findings

- BiRRe is documented as a FastMCP server exposing curated business tools over hidden BitSight OpenAPI-generated tools.
- The current README describes `standard` and `risk_manager` use cases, with tools for company search, rating retrieval, interactive search, subscription management, and company requests.
- The architecture document explicitly supports business tools that orchestrate multiple internal API calls.
- `src/birre/config/settings.py` currently allows only `standard` and `risk_manager` contexts.
- `src/birre/application/server.py` currently registers the common rating tool for all contexts, adds standard search by default, and adds the richer risk-manager tools only for `risk_manager`.
- BitSight alert and finding endpoints exist in the local API endpoint docs, including alert listing/latest endpoints and company finding endpoints.

## Candidate Implications

- Deterministic BitSight data retrieval, enrichment, and priority classification are likely a good fit for BiRRe's existing MCP/business-tool model.
- Durable ticket/documentation state, scheduling, retries across days, and Jira synchronization may need a separate storage/orchestration boundary unless BiRRe is intentionally expanded beyond MCP serving.
- A new context such as `alert_workflows` or `monitoring` may preserve the old interactive contexts while exposing automation-specific tools.
- The agent boundary should likely be text generation and judgment-heavy synthesis, while BiRRe owns repeatable data gathering, schema normalization, classification, and state-change proposals.
- A BiRRe-owned alert queue may reduce agent coordination burden, but it introduces durable state, idempotency, locking, replay, and failure semantics that the current MCP server does not appear to own.
- Direct Jira integration may be simpler than designing a generic ticket interface, but it would make BiRRe a multi-system workflow server rather than a BitSight-only server.
- The first useful slice can preserve the workflow promise with stable work-item IDs and deterministic ticket/action candidates before adding a durable queue.
- If Jira is the durable ticket record, BiRRe may still need minimal local correlation/audit state rather than full internal ticket storage.

## Open Research Questions

- Which BitSight alert endpoint and payload shape corresponds to the user's configured alert trigger?
- What fields are required to map an alert to a company GUID, finding/risk vector, rating event, and due date?
- What is the intended documentation/ticket schema before Jira synchronization exists?
- Does ticket state need to be queryable via MCP tools, a CLI command, a local database/file store, or all three?
- What schedule/runtime will run the workflows: external scheduler calling MCP/CLI, a long-running service, or manual agent invocation?
- Which parts require LLM-authored text versus deterministic templates and rule-based enrichment?
- If BiRRe owns an internal alert queue, what guarantees are required: deduplication, retry count, per-item status, lock/lease, audit log, and resume-after-crash?
- If Jira is the ticket source of truth, what minimum local state still remains necessary for idempotency and mapping BitSight alert/finding IDs to Jira issue keys?
