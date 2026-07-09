# Simplifier Stance

## Preserved Expectation

BiRRe should help turn BitSight alerts into repeatable operational action: enrich alerts, classify priority, create or update actionable ticket documentation, review open items for resolution, and summarize due work for management.

## Simplify Now

- Treat the internal alert queue as a delayed capability, not a Phase 1 foundation. A `work on next item in queue` tool sounds small, but it implies durable state, idempotency, locking/leases, retry semantics, replay, audit history, and crash recovery. That is too much infrastructure before the alert enrichment/classification loop is proven.
- Start with batch-in, structured-work-items-out. BiRRe can accept or fetch the day's alerts, enrich/classify them deterministically, and return normalized items that an agent or runner can process one by one. This preserves the product promise without making BiRRe a queue manager yet.
- Avoid a generic ticket-system abstraction. The only real target named is Jira, and no second ticket system exists. A generic interface now would be design theater unless a second backend or offline-first requirement is validated.
- Do not add internal ticket storage as a parallel source of truth by default. If Jira is the long-term operational home, local storage should be limited to the minimum needed for idempotency and mapping, not a competing ticket database.

## Delay Until Proven Necessary

- Internal alert queue with next-item claiming, status transitions, retries, and resume-after-crash.
- Full internal ticket/documentation store.
- Generic ticket backend abstraction.
- Direct Jira write automation beyond the minimal create/update/close operations needed once the ticket schema and idempotency keys are known.
- Scheduling/runtime ownership inside BiRRe. Let an external runner, CLI, or agent invocation drive the first useful slice unless evidence shows BiRRe must own scheduling.

## Minimal First Useful Slice

Build deterministic BiRRe workflow primitives for one daily batch:

1. Intake a batch of BitSight alert references, or fetch the latest alert batch if the endpoint mapping is known.
2. Enrich each alert with company and finding state.
3. Classify each item into the four agreed priorities.
4. Emit structured ticket candidates for priorities 1-3, including stable idempotency keys and enough fields for Jira later.
5. Emit a due-review summary from supplied open-ticket/work-item data, without owning the ticket store.

What remains after this slice: an agent or runner still splits the returned batch, drafts narrative where needed, and performs or simulates ticket creation. BiRRe owns repeatable BitSight data gathering and classification, not queue orchestration or durable ticket lifecycle yet.

## Assumptions To Validate

- The daily alert volume is small enough that batch processing is operationally tolerable.
- The alert payload contains stable identifiers that can map to company, finding, priority trigger, and future Jira issue keys.
- Priority classification can be deterministic from BitSight data and user-provided rules, without LLM judgment in the critical path.
- Jira can be the system of record for open/closed ticket state once integration begins.
- Only minimal local state is needed for idempotency, such as alert/finding identifiers mapped to Jira issue keys.
- The first operator experience can tolerate an agent/runner iterating over batch results rather than calling `work on next item`.
- Management summaries can be generated from enriched due-ticket inputs without BiRRe storing the entire ticket history.

## Confidence

0.84. The strongest simplification is delaying the internal queue, because it adds state-machine infrastructure before the core BitSight workflow value is validated. Direct Jira later is plausible and simpler than a generic abstraction, but the minimum local-state requirement must be tested before ruling out all storage.
