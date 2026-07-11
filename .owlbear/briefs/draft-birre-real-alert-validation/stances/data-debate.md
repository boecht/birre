# Data Quality Critic Dialogue

## Initial Position

The initial position required an envelope-discriminated normalized schema: numeric `start_rating`/`end_rating` movement for rating events, letter-grade `start_grade`/`end_grade` plus `risk_vector` for risk-category events, and no coercion between them. It treated alert details as primary event evidence, company history as corroboration only, `alert_date` as the timeline date, and `start_date` as separate context. It proposed conservative category normalization, strict pre-scoring validation, and pagination until exhaustion or an explicit bound with every returned date checked against the requested lower bound. It preserved all sequenced Jira, lifecycle, broader-category, and finding-correlation work.

## Critic Cycle 1

### Critic Challenge

The Critic accepted the core data-integrity posture but identified seven weaknesses:

1. A single one-day difference between `alert_date` and `start_date` cannot prove their complete semantics; timezone or truncation effects remain possible.
2. One sampled agreement between `trigger` and `details.risk_vector` cannot justify treating every future disagreement as corrupt or quarantining the whole alert.
3. The proposed envelope discriminator names were stronger than the evidence available to the panelist, which had not inspected source or schema directly.
4. The initial mapping promised provenance while omitting observed `rating_threshold` and `threshold_grade` fields.
5. Calling alert details "authoritative" overstated an evidence-backed design precedence as an established source property.
6. Pagination incompleteness was covered, but deterministic ordering and selection of a bounded subset were not.
7. Repeated-run stability testing was prudent but was phrased as though instability had already been observed.

The Critic also exposed blind spots around empty results, timezone/date-only semantics, the interaction between capped retrieval and validation, and the risk that quarantine could silently swallow legitimate schema variants.

The Critic rated the initial position at **0.68 confidence** with **medium pressure** and said another full cycle was unnecessary because the defects were concentrated in overclaim wording and unmapped evidence rather than the core posture.

### Modeler Response

Accepted the date-semantics challenge. The final stance says the observed difference makes substitution unsafe but does not prove the full meaning of either field. It explicitly retains timezone semantics as unresolved.

Accepted the category-agreement challenge. The final stance validates `trigger` and `risk_vector` independently, preserves both on conflict, excludes only category-dependent scoring, and does not discard the whole alert. Equality remains an observed hypothesis rather than a universal contract.

Accepted the discriminator-evidence challenge. The final stance treats the named variants as supported by available research evidence but requires source/schema confirmation before fixing the implementation contract.

Accepted the provenance challenge. `rating_threshold` and `threshold_grade` are now first-class optional evidence in their respective typed variants.

Accepted the authority-language challenge in part. The final stance states alert-detail precedence as the required design rule for event-specific evidence, not as proof that an upstream source is infallible. It stands firm that company history cannot substitute for missing alert movement because the sources make different claims.

Accepted the bounded-selection challenge. The final stance requires deterministic ordering, a tie-breaker, stable-identity deduplication, explicit completeness state, and counts. It rejects any unsupported claim that a capped prefix is representative.

Accepted the stability-wording challenge. Repeated runs are described as a prudent check, not as evidence of observed instability.

Added explicit `valid`, `incomplete evidence`, `conflict/unknown`, `malformed`, `bounded/incomplete`, and `complete empty` states. Malformed evidence is excluded from deterministic projection while a sanitized diagnostic remains visible, preventing quarantine from becoming silent record loss.

## Exit Decision

The Critic stated that another full cycle was not warranted without new source/schema evidence. The position was hardened around every identified weakness while preserving the central judgment: schema is the contract, numeric and grade movement must remain distinct, alert and company-history evidence must not be substituted, and pagination bounds must remain explicit. The loop exits after one complete cycle.
