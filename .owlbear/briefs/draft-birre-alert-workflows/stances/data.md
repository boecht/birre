# Data Quality Stance

The first module should be a loss-aware batch ingestion and normalization boundary, not a ticket workflow and not a durable queue. Its contract is to fetch v2 alert trigger records, normalize them without hiding source ambiguity, enrich distinct companies through the existing v1 company profile path, and return a batch whose gaps are explicit enough for later priority, Jira, finding, and closure workflows to make defensible decisions.

The strongest data position is this: v2 alerts are trigger/provenance records, not the full finding-remediation truth. Their expanded details may contain rating change and risk-vector signals, but the module must not assume those details contain complete finding payloads, remediation state, due-date semantics, or stable finding identities. Richer detail from v1 `/companies/{guid}/findings` and `/insights/rating_changes` should remain a named downstream/research boundary until the first module proves exactly what v2 alert details can and cannot support.

# Schema and Validation Reasoning

The first-module output needs three explicit layers:

1. Run metadata: requested lower-bound date, actual v2 query parameters, endpoint, retrieval timestamp, page size, total pages retrieved, total source count when supplied, warning flags, and whether pagination completed normally.
2. Normalized alert trigger records: `alert_guid`, `company_guid` when present, `company_name`, `alert_type`, `alert_date`, `start_date`, `severity`, `trigger`, folder identifiers/names, normalized detail summary fields, `details_raw`, source page metadata, and raw/source provenance.
3. Company enrichment records keyed by `company_guid`: the v1 company profile fields already needed for ticket decisions, including rating and profile fields, plus enrichment status and source provenance.

Page shape validation must happen before normalization. The v2 alert response is expected to have `count`, `links`, and `results`; if that envelope is absent or malformed, the module should fail the run rather than silently process a partial shape. Alert-record validation should be stricter for records that can drive company workflows than for the whole endpoint: missing `alert_guid` is a data-integrity error for deduplication and audit; missing `company_guid` is not automatically invalid because the source schema does not guarantee it for every alert type. Records without `company_guid` should be retained as non-enrichable trigger records with an explicit warning and excluded from company enrichment, not dropped.

The first module must not synthesize finding IDs, rating-event IDs, or remediation state from message-like text. Text fields can be preserved and summarized, but identity must come from explicit source fields. If later workflows need finding-level identity, that is the boundary where v1 findings or rating-change endpoints become required.

Validation boundaries should be explicit:

- Validate v2 page envelope before iterating.
- Validate each alert trigger record before normalization.
- Deduplicate enrichment calls by distinct `company_guid` before calling v1 company info.
- Validate each v1 company enrichment result before joining it back to alerts.
- Validate the final batch schema before returning it to an agent or runner.

Raw preservation is not optional. The v2 alert spec and descriptions appear semantically weak in places, and the fresh findings suggest expanded details may be incomplete for remediation. The normalized schema should therefore preserve raw alert records and raw details alongside normalized fields so later modules can recover from over-narrow initial assumptions.

# Identity and Normalization Position

Company GUID should be the primary subject identity for later Jira correlation because the operational ticket tracks the company/rating/finding situation, not the alert object itself. Alert GUID remains the trigger identity for provenance, deduplication, replay, and audit.

Deduplication within a run should be primarily by `alert_guid`. If the same `alert_guid` appears with conflicting company GUID, alert type, date, or trigger fields, that should be surfaced as an anomaly rather than hidden by a composite key. A secondary derived work-item key may combine `company_guid`, alert type, and alert date for later ticket grouping, but it must not replace the source alert identity.

The join shape is one-to-many: one company can have many alerts. Company enrichment must therefore fan in to one v1 company lookup per distinct `company_guid`, then fan out into normalized alert/company records. Per-alert company refetching would be a wasteful and noisier data path.

# Pagination and Freshness Risks

The v2 alert endpoint uses `limit`/`offset` pagination with `count`, `links`, and `results`. The module should follow `links.next` or compute the next offset only within the documented response shape, recording page offset, limit, retrieved count, and terminal condition.

The lower-bound semantics are a load-bearing risk. Fresh evidence says `alert_date_gte` exists, but the local spec may describe it as filtering `last_seen >=` rather than simple `alert_date >=`. That distinction matters. If the filter is really last-seen based, it can resurface alerts and provide a weak recency axis despite the absence of `updated_at`; if it is event-date based, changed alerts may not resurface. The first module should record the exact parameter used and treat the run as a retrieval snapshot, not as a proven incremental cursor.

Offset pagination over a live alert set can lose records, not merely duplicate them, because new or re-seen alerts can shift offsets between page requests. Within-run deduplication handles duplicates but not skipped rows. The first module should expose pagination warnings when `count` drifts, pages are empty before expected exhaustion, `links.next` is inconsistent, or retrieved totals do not match the source count. Persistent cursor state is not required for this first module, but the output should be honest that stateless pagination is not a full exactly-once ingestion guarantee.

# Key Trade-offs

Including v1 company profile enrichment in the first module is acceptable because the capability already exists and company context is immediately useful for the next ticket decision. Including v1 findings and rating changes in the same first module is not yet justified. That would mix trigger intake with unresolved finding-detail research and expand the schema before the alert contract is proven.

The module should prefer explicit partial records over silent dropping. A non-enrichable alert without `company_guid`, a malformed detail payload, or a failed company lookup should remain visible in the batch with a validation status. Dropping these records would corrupt operational counts and make the system look cleaner than the source data.

No internal queue should be introduced at this boundary. Queue semantics require idempotency, retry, leases, ordering, replay, and audit decisions that are larger than the first data contract. A normalized batch with stable identities and provenance is the correct first module boundary.

# Warnings

- Do not treat v2 alert details as complete finding payloads until verified against actual examples.
- Do not infer remediation or due-date state from message text.
- Do not treat `count == retrieved` as a durable correctness proof under offset pagination.
- Do not make `company_guid` globally required for every source alert, but do require it before company enrichment or company-ticket correlation.
- Do not collapse source provenance; retain endpoint, query params, page metadata, retrieval timestamp, and raw details.
- Do not build final priority classification on this first schema until the missing rating-drop/finding-detail source is resolved.

# Confidence

0.78. The stance is high-confidence on raw preservation, explicit validation boundaries, company GUID as subject identity, alert GUID as trigger provenance, and deferring finding-level enrichment. Confidence is lower on the exact `alert_date_gte` semantics and on whether v2 expanded details will be sufficient for any rating-drop subcase; those must be verified with real endpoint responses before cursor or classification design hardens.
