# End-User Stance Critic Debate

## Cycle 1 - Initial Position

The initial position proposed one timeline with separate `Numeric rating` and `Risk-vector grade` columns. Numeric rows would show `630 -> 620 (delta -10)`, grade rows would show `C -> D`, and the inapplicable cell would contain an em dash. Full provenance would live in a token-keyed evidence ledger below the table. `alert_date` would be the event date, while company-history movement and finding links would remain separate concerns.

## Cycle 1 - Critic Challenge

The Critic found the display architecture unsound:

- BitSight itself places numeric and grade transitions in one Alert column, so the claimed need for two movement columns lacked evidence.
- Two movement columns would guarantee a sparse, wide table and weaken plain-text Jira readability.
- An em dash would conflate not-applicable data with missing data and could be inaccessible to screen-reader users.
- A detached source ledger would add lookup and working-memory cost.
- The stance invoked UI fidelity for dates while departing from the UI structure without a governing principle.
- `alert_date` was verified only in observed evidence; missing-date and ordering behavior were unspecified.
- Numeric delta rendering introduced a derived value and unexplained asymmetry.
- Company and monitored-scope context, label-source reconciliation, scaling, and manual-edit fragility were not adequately addressed.

The Critic rated the draft at **0.55 confidence** and found its safety constraints stronger than its central presentation rationale.

## Cycle 1 - End-User Response

Accepted the core challenge. Preventing false equivalence does not require separate sparse columns. The stance changed to a single `Movement` column with explicit type prefixes, explicit unavailable/conflict states, inline-oriented provenance, and defined missing-date behavior. It also added a human-label cross-check and prohibited silent company-history substitution.

## Cycle 2 - Revised Position

The revision proposed:

- `Event date | Category / risk vector | Movement | Evidence`.
- `Rating: 630 -> 620 (change -10)` and `Risk-vector grade: C -> D`.
- Visible label conflicts when `trigger` and `details.risk_vector` disagree.
- `alert_date` as the observed UI event date, with distinct `start_date` retained as period evidence.
- Full GUID and field provenance inline.
- Explicit missing movement and company-history fallback labels.
- A per-company default with Company added only for multi-company exports.
- Date-window and truncation disclosure.

## Cycle 2 - Critic Challenge

The Critic found the revision substantially stronger but identified remaining contradictions:

- Adding `(change -10)` departed from the observed BitSight display and gave numeric movements a magnitude cue that grades lacked, reintroducing false equivalence through asymmetric emphasis.
- Full GUID and field metadata inline would make Jira rows wrap and undermine the intended scan path.
- The claim that type prefixes prevent equivalence was plausible but not directly evidenced by user testing.
- Label-conflict handling was prudent but based on a failure shape not observed in the sample, and numeric-event labels needed the same visible-label rule.
- Assuming a per-company default conflicted with the source's explicitly multi-company context.
- Same-day ordering, truncation detection, and a presumed ticket date window needed tighter qualification.

The Critic rated the revision at **0.72 confidence** and said the numeric-delta contradiction and company-context assumption still prevented decisive mediation handoff.

## Cycle 2 - End-User Response

Accepted the decisive objections and hardened the position:

- Removed numeric deltas entirely. Both measurement systems now show only typed endpoints and direction.
- Retained Company in every timeline row so evidence remains meaningful outside ticket context.
- Restored a compact `Source` token in the table, but made it readable (`BitSight alert A1`) and required the full source register immediately after the table. This deliberately trades one verification lookup for a usable primary scan path.
- Applied `trigger` as the human label across event types, with the risk-vector field used as a cross-check where applicable.
- Required explicit partial-evidence disclosure only when pagination or cap signals establish incompleteness; otherwise the workflow must not claim completeness.
- Required deterministic source ordering for same-day records without inventing timestamp precision.

The final position keeps the Critic's strongest insight: visual co-location is acceptable only when each row names its measurement type and no cross-scale magnitude cue is introduced.

## Debate Outcome

The position is hardened enough for mediation. The remaining uncertainty is empirical rather than conceptual: representative Jira rendering and real missing/conflict cases still need validation during the correctness proof.
