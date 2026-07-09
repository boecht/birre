# BiRRe Next-Step Sequencing Research Notes

## Verified findings

- The prior alert-workflow discovery exists at `.owlbear/briefs/draft-birre-alert-workflows/` and frames the expansion as an existing-feature/refactor.
- The prior discovery identifies alert intake, enrichment, deterministic classification, Jira documentation, open-ticket review, due-ticket review, and management summaries as the target workflow areas.
- The prior research notes say BiRRe already supports business tools that orchestrate hidden BitSight API tools, and that alert/finding endpoints exist in local API docs.
- The prior research notes also identify unresolved questions around alert payload shape, ticket schema, runtime scheduling, LLM-authored text boundaries, queue guarantees, and Jira/local-state correlation.
- `README.md` explains BiRRe's current user-facing purpose, contexts, tools, setup, configuration, and documentation entry points.
- `docs/ARCHITECTURE.md` explains the FastMCP layering, hidden OpenAPI tools, exposed business tools, context-specific registration, stateless server factory, and API-version strategy.
- `AGENTS.md` is a minimal pointer to `.github/copilot-instructions.md`; it does not itself bridge future agents into the alert-workflow expansion or OwlBear process context.

## Candidate implications

- Broad BiRRe documentation cleanup is not obviously the next bottleneck: the current architecture and tool model are already reasonably discoverable.
- A narrow agent-facing bridge may be more valuable than broad documentation work: future agents need to connect the existing BiRRe architecture, the prior alert-workflow discovery, and the intended OwlBear process without repeating rediscovery.
- Broad company knowledge-base ingestion is weakly justified as a first move unless it is pulled by concrete questions from the alert/Jira workflow.
- The strongest sequencing candidate is likely a decision-oriented readiness slice: use the prior brief as anchor, inventory existing docs, define the smallest agent/process and knowledge prerequisites, and then choose the first implementation move.
- The biggest known feature uncertainties remain operational and schema-specific: alert payload shape, Jira ticket schema, runtime ownership, LLM-vs-deterministic boundaries, and correlation/audit state.

## Open research questions

- What exact first feature or workflow slice will Phase 2 treat as the anchor when making the sequencing decision?
- Which internal company knowledge is actually necessary for the first feature: supplier ownership, risk policy, Jira workflow, priority definitions, communication templates, or exception handling?
- What form should agent-usable documentation take if selected: a brief-local handoff, repo-level instructions, a process README, memory entries, or all of these in sequence?
- What is the minimum evidence needed to prove knowledge-base ingestion has value before expanding ingestion scope?
- Should the next action produce only a decision record, or also a small agent handoff artifact that can be reused by the builder/planner?
