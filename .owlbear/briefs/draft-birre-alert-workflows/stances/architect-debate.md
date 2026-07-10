# Architect Critic Debate

## Initial Architect Position

The first alert workflow module should live inside BiRRe as a workflow-facing business tool surface that performs deterministic BitSight-only alert intake and company enrichment: fetch v2 `GET /alerts` with `alert_date_gte`, `expand=details`, pagination, normalize alert records, dedupe/enrich distinct company GUIDs via existing v1 company-info capability, and return a batch keyed primarily by company GUID with alert GUID as trigger provenance.

It should not introduce a durable queue, Jira mutation, final priority classification, or management-summary generation. The broader roadmap boundary should keep BitSight retrieval, normalization, enrichment, deterministic classification once inputs are known, and action-candidate generation in BiRRe; scheduling, retries, ticket mutation, and durable lifecycle state should live in an adjacent orchestration/Jira layer unless later evidence proves BiRRe needs a minimal correlation/audit ledger.

## Critic Challenges

The Critic accepted the sequencing and exclusion of queue/Jira/final classification from the first module, but raised several material challenges:

- `alert_date_gte` may not mean alert event date. The Critic reported that the v2 spec text describes `alert_date_gte` as filtering `last_seen`, while other alert-date filters may use different semantics. That makes the filter choice load-bearing rather than a minor validation risk.
- A stateless daily pull over date-granular, potentially `last_seen`-based data cannot claim cross-run idempotency. Inclusive date windows can re-surface alerts, and the first module only deduplicates within a run unless another layer owns correlation state.
- Offset pagination over a live filtered set can skip or duplicate records if alerts enter or move in the result set during traversal.
- A company-keyed batch can accidentally collapse multiple distinct alerts for the same company if alert provenance is singular rather than a collection.
- Calling the v2 prerequisite only a wiring task understates new pagination, expansion, normalization, and workflow orchestration work.
- Deterministic priority classification is not yet evidenced because no priority rule schema exists in the brief.
- The likely sources for richer rating-drop/finding details are leads, not proven dependencies.

## Architect Response

The filter-semantics and cross-run idempotency critiques are accepted. The final stance now treats `alert_date_gte` as a load-bearing validation point and explicitly limits the first module's idempotency claim to within-batch deduplication unless a caller, Jira layer, or later minimal ledger owns cross-run correlation.

The company-keying critique is accepted. The final stance keeps company GUID as the downstream subject identity but requires alert provenance to be retained as a collection per company. A company record with only one alert trigger is rejected as lossy.

The pagination critique is accepted as a contract warning. The final stance recommends following the API's `links.next` contract where possible and preserving source pagination metadata so unstable or partial runs can be diagnosed.

The "wiring only" critique is partially accepted. The final stance still says a new v2 bridge is not required, but it no longer minimizes the work to allowlist edits. Alert endpoint exposure plus pagination, details expansion, loss-aware normalization, and company enrichment orchestration are new behavior.

The deterministic classification critique is accepted. The final stance moves final priority classification out of module one and frames later deterministic classification as conditional on known rules, not as a settled current capability.

The richer detail-source critique is accepted. The final stance treats v1 `/companies/{guid}/findings` and `/insights/rating_changes` as likely leads for a later enrichment stage, not as proven sources.

## Final Adjustment

The final stance remains strongly in favor of a BiRRe-owned first module for BitSight alert/company batch intake, but it is now narrower and more explicit about what it does not guarantee. The first module proves the retrieval and normalization contract; it does not solve cross-run lifecycle state, Jira mutation, full finding remediation, or priority rules.
