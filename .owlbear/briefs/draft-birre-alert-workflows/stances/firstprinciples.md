# First-Principles Stance

## Irreducible Job

BiRRe's irreducible job is to turn BitSight signals into reliable operational facts and proposed actions: identify what changed, enrich it with the current company/finding context, classify it by stable rules, and expose enough structured evidence for a human or agent to decide and communicate next steps.

The irreducible job is not "run the whole workflow." It is narrower: preserve a trustworthy chain from BitSight event -> enriched finding -> priority/criticality -> action candidate -> evidence bundle.

## Assumptions That Need Pressure

- An internal queue is not inherently simpler than batch processing. It only becomes necessary if BiRRe must own retry, deduplication, partial progress, ordering, locks/leases, or resume-after-crash semantics. Without those guarantees, a queue is mostly a UI shape for the agent: "next item" instead of "item N from this batch."
- Direct Jira integration may be simpler than a generic ticket abstraction, but it does not eliminate state. At minimum, the system still needs idempotency and correlation between BitSight alerts/findings and Jira issue keys, plus a way to distinguish "not yet ticketed," "ticket open," "resolved," and "intentionally ignored."
- "Ticket storage" and "ticket source of truth" are different claims. Jira can be the source of truth for work items while BiRRe still keeps a small correlation/audit ledger. Treating those as the same decision may overstate the queue/storage choice.
- Agent convenience should not be mistaken for system responsibility. A `work on next item` tool may improve ergonomics, but it also asks BiRRe to decide what "next" means and to remember that decision.
- Management summaries do not require BiRRe to author prose. The deterministic core may only need ranked, attributed, freshness-checked evidence. The agent can write narrative once the facts and ordering are fixed.

## State: Necessary vs Convenient

Necessary state appears limited to stable identity and lifecycle correlation:

- BitSight alert/finding/company identifiers needed to deduplicate and re-check facts.
- Mapping from BitSight entity/event to external ticket/document key, if tickets exist.
- Current lifecycle marker sufficient to avoid duplicate ticket creation and unsafe closure.
- Timestamps/source snapshots or audit events sufficient to explain why a priority or closure proposal was made.

Convenient but not yet proven necessary:

- A durable internal alert queue with per-item worker states.
- A generic ticket-system abstraction before a second ticket backend exists.
- Rich internal ticket/document storage if Jira becomes the durable work item record.
- Agent-facing `next item` state unless the workflow genuinely needs resumable multi-step processing across failures or sessions.

## Deterministic vs Agent-Authored Boundary

Keep deterministic:

- Alert retrieval and normalization.
- Company/finding enrichment.
- Priority and criticality classification rules.
- Deduplication/correlation checks.
- Closure eligibility checks based on current BitSight state.
- Ranked evidence bundles for due-ticket review.

Allow agent-authored, but evidence-bound:

- Ticket descriptions and management prose.
- Explanation of business impact.
- Suggested next-step wording.
- Human-facing summaries of top risks.

The agent should not invent classification, lifecycle transitions, or closure eligibility. It should transform already-computed facts into usable communication.

## Accidental Complexity Candidates

- Treating "automation" as requiring BiRRe to become a scheduler or worker runtime.
- Treating "agent can process one item at a time" as requiring an internal queue rather than a deterministic batch plus item IDs.
- Designing ticket portability before Jira has failed as the concrete target.
- Storing complete ticket bodies internally when only correlation, status, and audit may be required.
- Combining alert intake, ticket lifecycle, prioritization, and summaries into one indivisible workflow instead of testing which shared primitives they actually need.

## Open Questions

- What failure must be recoverable without human reconstruction: duplicate ticket creation, missed alert, partial enrichment, bad closure, or lost summary context?
- Does "next item" need durable ordering and claiming, or only a convenient way for an agent to iterate a known batch?
- If Jira is source of truth, what exact local correlation/audit fields remain necessary for idempotency and explainability?
- Who is allowed to close a ticket: deterministic rule, agent proposal, or human approval after evidence review?
- Are the four priority classes purely rule-based, or do any require judgment that must be surfaced as uncertainty rather than classification?
- Is the daily alert trigger already the durable event log, or can alerts disappear/change such that BiRRe must snapshot them?

## Confidence

0.82. The core distinction is strong: BiRRe must own trustworthy BitSight-derived facts and deterministic action proposals; durable queue/work-item ownership is only justified by explicit recovery and idempotency guarantees. The main uncertainty is the real alert payload and whether the existing trigger already provides durable delivery semantics.

## 2026-07-09 Module 1 First-Principles Check

### Irreducible Job

Given a trusted lower-bound date, retrieve every BitSight v2 alert at or after that date, preserve enough provenance to re-fetch or audit it, and emit deterministic normalized records for later workflow stages.

This is source intake plus normalization, not the whole alert workflow. Jira lookup, prioritization, v1 enrichment, ticket mutation, closure logic, and reporting are downstream.

### Load-Bearing Assumptions

- `alert_date_gte` may not mean ingestion time or last update time; the workflow must verify what operational event it filters.
- `expand=details` may not include every later priority input, so intake should preserve raw/source details rather than flattening lossy fields too early.
- v2 alert `guid` must be verified as durable across repeated pulls before it becomes the correlation key.
- Pagination correctness matters: duplicate handling within a run is part of intake, not optional cleanup.

### Necessary State

- Input lower-bound date and exact API query used.
- Alert source ID or explicit fallback identity rule.
- Alert date and other source timestamps available.
- Company identifiers needed for later v1 enrichment.
- Source API version, endpoint, query parameters, pagination provenance, and raw/source detail.
- Duplicate suppression within one run.

### Convenient But Later

- Persistent cursor storage.
- Jira issue keys and ticket lifecycle state.
- Priority classification and v1 enrichment results.
- Human-readable reporting text.

### Confidence

0.82. The first module is well chosen if it is kept to reliable v2 intake and loss-aware normalization; the two riskiest claims are date semantics and stable alert identity.

### User Refinement

Company GUID should be the primary subject identity for Jira because the company is what the ticket tracks; the alert is the trigger that causes the system to inspect the company. This shifts the first module from pure alert intake to alert-triggered company intake/enrichment, while preserving alert GUID as provenance and duplicate-control data.

The missing web-GUI rating-drop/finding-result details are a separate evidence gap. Do not assume alert endpoints contain that data until the API source is identified.
