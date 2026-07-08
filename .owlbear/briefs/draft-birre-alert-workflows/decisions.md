# BiRRe Alert Workflow Discovery Decisions

## D1 - 2026-07-06 - Project Type

**Status quo:** BiRRe is an MCP server focused on curated interactive BitSight tools.

**Decision to make:** Should the expanded alert/ticket/summary workflows live inside BiRRe, in a new project, or be split?

**Options considered:**

- A: Implement everything in BiRRe.
- B: Create a new automation project and treat BiRRe as the BitSight integration layer.
- C: Extend BiRRe with deterministic BitSight workflow primitives and keep ticket storage/sync plus scheduling/orchestration outside or in an adjacent package.

**Chosen:** Existing-feature/refactor.

**Rejected:** Net-new wrapper/orchestrator for the first framing pass, because the deterministic BitSight retrieval/enrichment/classification work fits BiRRe's existing business-tool-over-API-orchestration architecture.

**Source inputs:**

- User's current need has shifted from interactive API use toward three automated workflows for alerts, ticket lifecycle review, and management summaries.
- Local repo evidence shows BiRRe already implements business tools that orchestrate hidden BitSight API calls.

## D2 - 2026-07-06 - Discovery Rigor

**Status quo:** The workflows are personal/team operational tooling, not a public product.

**Decision to make:** How rigorous should the ideation pass be?

**Options considered:**

- Tool: standard discovery for a single-user/internal utility.
- Shared: stronger discovery and challenge pass for a reusable operational workflow.
- Production: stricter review gates for a durable operational system.

**Chosen:** Shared.

**Rejected:** Tool, because the queue/ticket lifecycle and priority schema have enough state and consequence to justify stronger framing. Production, because this is not currently scoped as an external-facing or fully governed system.

**Source inputs:**

- User selected Shared rigor.

## D3 - 2026-07-06 - Ticket and Queue Boundary

**Status quo:** BiRRe has no internal durable alert queue, documentation ticket store, or Jira integration today.

**Decision to make:** Should BiRRe own alert queue state, ticket state, Jira interaction, or only deterministic BitSight enrichment/classification primitives?

**Options considered:**

- A: Internal alert queue in BiRRe; agent calls a `work on next item` style tool.
- B: No internal queue; return today's alerts as a batch and let an agent/runner split and process them.
- C: Use Jira directly as ticket source of truth, with no separate internal ticket store.
- D: Add a generic ticket-system interface.

**Chosen:** Pending.

**Rejected:** Generic ticket-system interface for now, because the concrete workflow is Jira and KISS/YAGNI favors implementing the real integration when needed instead of abstracting before a second ticket system exists.

**Working challenge:** Internal queue is not rejected, but it is not yet justified as the first foundation. It should be added only if the workflow needs durable retry, deduplication, locking/leases, resume-after-crash, or ordering semantics that a batch plus stable work-item IDs cannot provide.

**Source inputs:**

- User is unsure about internal queue storage, but sees value in a server-managed queue so the agent can call `work on next item in queue` rather than manually split a batch.
- User thinks direct Jira integration may avoid a separate internal ticket store, given Jira is the stable long-term target.
- Simplification check recommended delaying the queue and starting with batch-in, structured-work-items-out primitives.
- First-principles check separated Jira as ticket source of truth from the still-possible need for minimal local correlation/audit state.
