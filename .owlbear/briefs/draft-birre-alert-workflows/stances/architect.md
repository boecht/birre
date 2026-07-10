# Architectural Stance

The first alert workflow module should be a deterministic BitSight intake-and-enrichment business capability inside BiRRe, but it must be scoped as a batch contract, not as a queue, ticket engine, or Jira workflow. The right first boundary is: fetch v2 alerts for a caller-supplied date window, request expanded details, traverse pagination, preserve raw/source provenance, normalize alert facts, group by company without collapsing distinct alert triggers, and enrich each distinct company GUID through the existing v1 company-info path.

Company GUID should be the primary subject identity for downstream ticket correlation. Alert GUID is not the primary ticket subject, but it is mandatory trigger provenance and must be retained as a collection per company when multiple alerts exist. A company-keyed output that stores only one alert trigger is structurally wrong because it would lose the per-alert facts needed for later classification, documentation, and closure checks.

# Structural Reasoning

BiRRe is the right home for the first slice because the slice is still BitSight-only orchestration: retrieve from BitSight, normalize BitSight records, enrich with existing BitSight company data, and return a stable work batch. That matches BiRRe's existing business-tool-over-hidden-API architecture better than a separate automation project would for module one.

The v2 prerequisite is surface and workflow logic, not a new bridge from scratch. BiRRe already has v2 OpenAPI server creation and a generic v2 OpenAPI call helper, but current runtime exposure is constrained to risk-manager company-request tools. The first implementation therefore needs alert endpoint exposure plus new pagination, expansion, normalization, and enrichment orchestration. Calling it only "wiring" would underscope the work; the bridge exists, but the workflow behavior does not.

The module should return normalized batch output rather than own durable queue state. A true internal queue would force BiRRe to own idempotency, retry counts, leases, ordering, replay, crash recovery, and audit semantics before the alert contract is proven. That is premature. The first module can still preserve the larger workflow promise by producing stable alert/company work items with enough provenance for a runner or later Jira layer to decide what to do next.

The broader roadmap boundary should be explicit: BiRRe should own deterministic BitSight retrieval, normalization, enrichment, and later rule-based candidate generation where the rules are known. Scheduling, multi-day retries, ticket mutation, and durable lifecycle state should remain outside the first module. A minimal local correlation/audit ledger may become necessary later, especially if Jira becomes the ticket source of truth but BiRRe still needs to map BitSight alert/finding/company identifiers to issue keys and decisions.

# Key Trade-offs

The narrow batch boundary gives up the ergonomic `work on next item` queue flow for now, but it avoids building a state machine before the data contract is trustworthy. That is the right trade-off. A queue can be added later if cross-run guarantees require it; removing a premature queue is harder.

Including v1 company enrichment in the first module is worth the small coupling because the existing company-info capability already supplies fields the downstream ticket decision needs. This should remain a v1 dependency unless v2 evidence shows equivalent fields. The coupling is acceptable because the module's real boundary is BitSight workflow enrichment, not v2 purity.

Final priority classification should stay out of module one. The roadmap can aim for deterministic classification, but no priority rule schema has been proven yet. The first module should expose the fields needed to design that classifier rather than smuggling an incomplete classifier into the intake layer.

Jira should not be abstracted behind a generic ticket-system interface yet. The concrete long-term target is Jira, and a generic interface would be invented architecture without a second backend. The right future boundary is direct Jira integration or an adjacent Jira runner once the normalized BitSight batch and correlation needs are clear.

# Warnings

The `alert_date_gte` semantics are load-bearing and not settled enough to treat as a harmless parameter choice. Fresh findings say v2 `GET /alerts` supports `alert_date_gte`, but the module must verify whether that filter is truly alert event date or effectively `last_seen`. If it is `last_seen`, then a stateless daily pull will intentionally re-surface older alerts and must be documented as overlap-prone rather than event-date-complete.

The absence of a documented `updated_at` field means cross-run idempotency cannot be waved away. Module one may remain stateless, but then its contract must say it deduplicates within a returned batch only. Cross-run duplicate handling belongs to the caller, Jira/correlation layer, or a later minimal ledger. Do not describe the first module as globally idempotent unless that owner exists.

Offset pagination over a live, filtered alert set can skip or duplicate records if the underlying result set changes during traversal. The implementation should follow the API's `links.next` contract where possible and preserve pagination metadata. If only offset is available internally, the output must include enough source metadata to diagnose partial or unstable runs.

The v2 alert `details` payload should be treated as useful trigger context, not as the full remediation/finding payload. Fresh findings indicate it includes rating movement and message-like detail fields, but likely not full finding remediation detail. Richer rating-drop and finding context should remain a separate enrichment stage, with v1 `/companies/{guid}/findings` and `/insights/rating_changes` treated as likely leads rather than proven dependencies.

The first module must be loss-aware in the concrete sense: preserve raw alert payloads, source endpoint/filter parameters, pagination metadata, alert GUIDs, alert types, alert dates/start dates, company GUIDs, folder/alert-set context, severity, trigger, and expanded details even when the normalized schema does not yet understand every type-specific field.

# Confidence

Confidence: 0.78.

The main architectural boundary is solid: BiRRe should own the first BitSight-only intake/enrichment batch, while queue, Jira mutation, final classification, and summaries stay out. Confidence is not higher because filter semantics, live pagination behavior, and the source of richer finding/rating-drop detail remain unresolved and can materially change the durability contract.
