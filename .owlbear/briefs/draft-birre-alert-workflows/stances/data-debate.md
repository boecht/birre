# Data Panel Critic Dialogue

# Initial Data Stance

The first draft stance treated the module as a loss-aware batch ingestion and normalization boundary. It required explicit source envelopes, normalized alert trigger records, company enrichment records keyed by `company_guid`, and run metadata. It also required raw preservation, page-shape validation, alert-record validation, company enrichment validation, and final batch validation.

The draft asserted that absence of `updated_at` means stateless pulls by `alert_date_gte` are at-least-once and duplicate-prone, recommended within-run deduplication by `alert_guid + company_guid`, and said missing `company_guid` or `alert_guid` should fail or mark the record partial. It also stated that v1 findings and rating changes should remain follow-up research until the first module proves whether v2 details lack needed data.

# Critic Challenges

The critic agreed that raw preservation, no synthetic finding IDs, and deferring v1 finding/rating-change enrichment were directionally sound. It raised six substantive challenges:

1. `alert_date_gte` may be misread. The critic found local spec evidence that `alert_date_gte` is described as filtering `last_seen >=`, not simply `alert_date >=`. This undermines any simple incremental-pull thesis based on event date.
2. No documented `updated_at` does not mean there is no freshness axis at all if `last_seen` exists as a filter. The first draft overstated the absence of freshness signals.
3. Hard-failing missing `company_guid` overreaches because the alert schema does not require it and some alert classes may not map cleanly to a subscribed company.
4. Some v2 alert field descriptions appear semantically unreliable, so the stance should be more explicit that normalized semantics are not fully grounded by the spec alone.
5. Offset pagination over a moving filtered set can skip records, not just duplicate them. Within-run deduplication is not enough to claim at-least-once ingestion.
6. Deduplicating by `alert_guid + company_guid` could hide anomalies where one alert GUID appears with conflicting company GUIDs. `alert_guid` should remain primary source identity, with conflicts surfaced.

The critic also flagged blind spots around incompatible alert-date query parameters, endpoint variants such as `/alerts/latest` and `/alerts/customer`, enrichment fan-in by company GUID, `scope=spm`, and the unreliability of `count` as a moving total.

# Revisions Made

The final stance accepts the critic's main corrections:

- It no longer treats `alert_date_gte` as a simple event-date lower bound. It names the lower-bound semantics as a load-bearing validation risk and requires the module to record exact query parameters used.
- It changes freshness language from "no freshness guarantee" to a narrower statement: absence of `updated_at` prevents a proven update cursor, while `last_seen` may still provide a weak recency axis.
- It distinguishes missing `alert_guid` from missing `company_guid`. Missing `alert_guid` remains a data-integrity problem for deduplication and audit; missing `company_guid` becomes a non-enrichable trigger-record condition rather than automatic invalidity.
- It changes deduplication to primary `alert_guid`, with conflicting company or alert fields surfaced as anomalies.
- It adds the record-loss risk from offset pagination over a live result set.
- It explicitly requires v1 company enrichment to deduplicate by distinct `company_guid` before joining back to alerts.
- It adds a warning that the v2 spec's field semantics are not strong enough to justify discarding raw payloads.

# Standing Position After Critic

The data stance remains firm that the first module is a normalized alert/company batch, not a queue, Jira workflow, final classifier, or finding-remediation engine. The critic materially improved the pagination and filter semantics, so the final confidence is reduced from the initial 0.84 to 0.78.
