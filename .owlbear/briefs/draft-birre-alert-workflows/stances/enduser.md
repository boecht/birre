# User Experience Stance

The first alert workflow module should feel like a review-ready intake packet, not a batch dump. The user needs to open the output and immediately understand which companies appeared in the alert window, what triggered review, what data was retrieved, what is still missing, and whether the run is trustworthy enough to hand off into classification or ticket drafting.

The right UX boundary is company-centered review with preserved per-alert provenance. Company GUID should be the main organizing identity because that matches the eventual Jira correlation model, but every alert GUID, alert type, date, severity, trigger, detail payload, folder/alert-set context, and source reference must remain visible under that company. A company with multiple alerts should read as one subject with multiple triggers, not as a collapsed single event.

# Usability Reasoning

Operational usefulness comes from reviewability, not just completeness. A technically correct list of normalized records still leaves the user doing the real work manually: checking coverage, identifying duplicate companies, separating facts from inferred fields, and explaining whether the batch is ready for the next workflow step.

The first module should therefore emit three layers:

- Company review groups: company identity, v1 profile enrichment, current rating and relevant profile fields, plus all associated v2 alert triggers.
- Run evidence: input date, applied filters, pagination count/links/offset coverage, number of alerts returned, number of distinct companies, enrichment successes/failures, and raw/source provenance.
- Review flags: normalization warnings, missing fields, unknown `alert_date_gte` semantics, no documented `updated_at`, and explicit notes where v2 details do not provide richer finding or remediation detail.

This should be management-summary-ready in shape, but not management-summary-generating yet. Safe summary structure means descriptive counts and coverage indicators: alerts by severity/type, distinct companies, companies with multiple triggers, enrichment failures, and unresolved data gaps. It should not name "top companies," assign final priority, or claim notability unless a later classification module has defined those rules.

# Key Trade-offs

Grouping by company improves operational scanning and future Jira correlation, but it risks hiding trigger-level nuance. The design must keep per-alert rows or nested records visible enough that a reviewer can audit why the company entered the packet.

Including v1 company enrichment makes the first module feel materially useful because the reviewer gets business context immediately. The trade-off is latency and partial-failure handling across one call per distinct company; the UX must expose enrichment status instead of silently producing uneven records.

Keeping raw/source payloads visible increases output size, but it protects trust. The reviewer needs a way to distinguish BitSight facts, BiRRe-normalized fields, and unresolved gaps, especially while the rating-drop and finding-detail source remains uncertain.

Avoiding priority labels and Jira mutation keeps module one honest. The output can prepare for classification by preserving fields and gaps, but it should not promise that downstream classification can happen without additional fetches. Fresh findings suggest richer detail may require v1 `/companies/{guid}/findings` or `/insights/rating_changes`, so the packet should state that limitation plainly.

# Warnings

Do not ship this as only `count`, `links`, and `results` with normalized alert records. That may satisfy the endpoint integration, but it underdelivers the operational workflow because the user still has to build the review view mentally.

Do not overcorrect by generating management conclusions. Counts, coverage, and gap indicators are appropriate; rankings, final priorities, ticket actions, and management prose are premature until the classification and documentation schema exist.

Do not imply coverage certainty beyond the API evidence. `alert_date_gte` semantics, alert mutation behavior, and the lack of documented `updated_at` mean the run can report what it fetched, not guarantee that no operationally relevant alert changed or was missed.

Do not bury missing finding/remediation detail inside raw JSON. If v2 `expand=details` gives rating-change percentages, risk vectors, and message-like fields but not full remediation payloads, the packet should mark that as an explicit enrichment gap rather than letting the user discover it during ticket writing.

# Confidence

0.82. The stance is strongly supported by the workflow goal and the D4/D5 boundary: first module equals alert intake plus v1 company enrichment, stopping before Jira mutation and final priority classification. Confidence is not higher because the exact ticket/documentation schema and richer rating-drop/finding sources remain unresolved.
