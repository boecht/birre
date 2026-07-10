# BiRRe Alert Workflow Discovery Context

## Current Problem Snapshot

BiRRe currently serves as a FastMCP server for interactive BitSight API use, with curated business tools over hidden BitSight API endpoints. The user's current operational need has shifted from interactive querying toward repeatable alert, ticket-documentation, closure, and management-summary workflows.

The central scoping question is whether these workflows should be implemented inside BiRRe, in a new project that consumes/includes BiRRe, or split across both.

## Project Type

Current classification: existing-feature/refactor.

The working intent is to evolve BiRRe from an interactive BitSight MCP server into a broader BitSight workflow server for the user's operational monitoring work.

## Depth / Rigor

Current tier: Shared.

The workflows are primarily for the user and possible support collaborators, but the classification, ticket lifecycle, and management-summary inputs need enough rigor to avoid silent underdelivery.

## Desired Workflow Areas

1. Daily new-alert intake from an existing BitSight alert trigger.
2. Alert enrichment: retrieve detailed finding data and company data.
3. Deterministic classification into four priorities.
4. Documentation creation for priorities 1-3, with Jira eventually likely but intermediate storage likely first.
5. Open-ticket review: enrich each open ticket with current company and finding state, then close tickets when the downgrade/finding has resolved before due date.
6. Due-ticket review: rate criticality, sort by priority and criticality, and generate a management summary for top findings.

## First Roadmap Module Candidate

The first module should be alert-triggered company intake and enrichment: given an input date, fetch all alerts from BitSight v2 `GET /alerts` with `alert_date_gte`, request expanded details, follow pagination, normalize alert records, then enrich each distinct company through the existing v1 company-info capability.

This is first chronologically because every later workflow depends on the alert batch: Jira lookup, new-ticket priority calculation, enrichment for ticket creation, existing-ticket update, later closure checks, and due-ticket reporting.

The first module should stop before Jira mutation and priority finalization. Its useful output is a complete, normalized alert/company batch that exposes the data needed for the next workflow decision: company GUID as the primary subject identity, company profile fields from v1, alert GUID as trigger/provenance, alert type, alert date/start date, folder/alert-set context, severity, trigger, details, raw/source provenance, and pagination/source metadata.

Two validation risks are load-bearing for this module: whether `alert_date_gte` is the right inclusive lower-bound filter for the operational workflow, and where the web UI obtains rating-drop/finding-result details if they are not exposed by the tested v1/v2 alert endpoints.

The v2 bridge is not absent, but it is not yet exposed for alert workflows. BiRRe already has a v2 OpenAPI server factory and generic v2 OpenAPI call helper; current server wiring creates v2 only for the `risk_manager` context and allowlists company-request tools, not alert tools. The dependency is therefore likely a small v2 alert-surface/wiring task, not a full v2 bridge from scratch.

Company enrichment remains a v1 dependency, but it should be included in the first module because the existing company-info capability already provides the required fields. The enrichment uses `v1/companies/{guid}` for `ipv4_count`, `people_count`, `homepage`, `description`, `current_rating`, and `rating_industry_median`.

## Current Architectural Signal

BiRRe already supports the pattern of exposing small business tools that orchestrate many hidden BitSight API tools. The existing architecture therefore supports deterministic enrichment/classification tools in principle.

Known current constraints:

- Runtime contexts are currently limited to `standard` and `risk_manager`.
- v2 API server creation is currently tied to the `risk_manager` context.
- v2 alert endpoints exist in the local OpenAPI docs, including `GET /alerts` with `alert_date_gte`, `expand=details`, `limit`, and `offset`.
- Current v2 tool allowlisting is limited to company-request tools, so alert-intake implementation would need v2 alert tool exposure before a business tool can call it.
- Jira/ticket-system interaction does not exist in the repo.
- There is no current durable ticket/documentation storage abstraction.

## Active Tensions

- MCP server as deterministic workflow engine vs separate scheduled automation app.
- BitSight-only scope vs multi-system workflow ownership.
- Agent-authored narrative text vs deterministic data gathering, classification, and state transitions.
- Internal alert queue/state vs returning a batch of normalized work items for an agent/runner to process.
- Intermediate ticket storage vs Jira as the primary ticket source of truth.
- Generic ticket-system interface vs direct Jira integration for the user's concrete workflow.

## Current Challenge Result

The internal queue should be treated as a capability to justify, not the default foundation. A `work on next item` tool is ergonomic, but it implies durable state, idempotency, retry, locking/leases, ordering, replay, audit, and crash recovery if it is more than a thin iterator over a batch.

The simpler first shape remains batch-in, normalized-work-items-out. For the first module specifically, BiRRe fetches alerts since a caller-supplied date, groups/enriches by company GUID, and emits stable normalized alert/company records. Later modules can classify and emit ticket/action candidates after the intake and enrichment contract is proven.

Jira can still become the source of truth for tickets. That does not eliminate all local state: BiRRe may still need a minimal correlation/audit ledger mapping BitSight alert/finding/company identifiers to Jira issue keys and lifecycle decisions.
