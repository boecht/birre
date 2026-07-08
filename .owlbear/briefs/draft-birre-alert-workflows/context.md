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

## Current Architectural Signal

BiRRe already supports the pattern of exposing small business tools that orchestrate many hidden BitSight API tools. The existing architecture therefore supports deterministic enrichment/classification tools in principle.

Known current constraints:

- Runtime contexts are currently limited to `standard` and `risk_manager`.
- v2 API server creation is currently tied to the `risk_manager` context.
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

The simpler first shape is batch-in, normalized-work-items-out: BiRRe fetches or accepts today's alerts, enriches each item, classifies it, and emits stable work-item IDs plus ticket/action candidates. That preserves the product promise while avoiding premature queue infrastructure.

Jira can still become the source of truth for tickets. That does not eliminate all local state: BiRRe may still need a minimal correlation/audit ledger mapping BitSight alert/finding/company identifiers to Jira issue keys and lifecycle decisions.
