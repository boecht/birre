# End-User Experience Stance

## User Experience Stance

The Jira-action timeline should preserve BitSight's event-log scan pattern without pretending that numeric company ratings and letter-grade risk-vector assessments are one scale.

Use one chronological table with these columns:

`Event date | Company | Category / risk vector | Movement | Source`

The `Movement` cell must identify its measurement type in words:

- `Rating: 630 -> 620`
- `Risk-vector grade: C -> D`

Do not calculate a numeric delta for grades. Do not add a numeric delta for ratings either: asymmetric quantification would visually privilege one scale and invite cross-scale comparison. The arrow records direction and endpoints; it does not claim that ten rating points and one letter-grade step are comparable severities.

Use the human-facing `trigger` value for `Category / risk vector`. For risk-category alerts, cross-check it against `details.risk_vector`. A disagreement must be displayed as `Label conflict - review`, not silently resolved. Preserve the API envelope type as provenance, not as the analyst-facing category.

Use `alert_date` as `Event date` because it matches the observed BitSight Alerts presentation. A distinct `start_date` is evidence about the measured period, not a replacement event date. If `alert_date` is absent, display `Event date unavailable` and place the row after dated events; do not silently substitute another date.

## Usability Reasoning

One typed movement column is clearer than separate rating and grade columns. Separate columns create a wide, sparse Jira table, while an untyped generic `Before -> After` column hides the semantic distinction. The explicit `Rating:` and `Risk-vector grade:` prefixes preserve a compact scan path and state the distinction at the point of use.

Retain `Company` even when a ticket is expected to concern one company. The source UI is multi-company, exported evidence may be reviewed outside its original ticket context, and repeating identity is cheaper than allowing a copied row to become ambiguous.

Keep the primary timeline compact. `Source` should contain a readable token such as `BitSight alert A1`, with an immediately following source register containing the full alert GUID, API envelope type, distinct period start, and source movement fields. Tokens must use words and stable row identifiers, not punctuation alone. The GUID remains plain provenance because there is no alert detail page; it must not be rendered as a fabricated link.

Missing or conflicting evidence must be explicit:

- `Movement unavailable - review` when alert-specific endpoints are absent.
- `Label conflict - review` when verified human-label sources disagree.
- `Event date unavailable` when `alert_date` is absent.
- Multiple problems remain visible together rather than one status masking another.

Company history may be shown only as `Company history corroboration` or `Company history fallback`. It must never populate an alert movement as though it came from that alert. A fallback is supporting company evidence, not an immutable alert event.

The timeline must state its requested date window and evidence coverage. When pagination or retention caps indicate more records exist, disclose the returned count and truncation next to the table. Same-day events must use a deterministic source order without implying a finer timestamp than the API provides.

## Key Trade-offs

- A source register adds one lookup for deep verification, but keeps full GUIDs and field names from destroying the timeline's primary scan path.
- Repeating Company consumes width, but preserves meaning when Jira content is copied, exported, or viewed without ticket context.
- Matching BitSight means preserving its event date, human label, and endpoint movement semantics. It does not mean copying every source column or treating its compact display as proof that the underlying scales are equivalent.
- Explicit review states are noisier than blanks, but blanks cannot distinguish unavailable, conflicting, and inapplicable data.

## Warnings

- Do not derive priority by comparing numeric rating movement with letter-grade movement. Priority scoring needs type-aware rules outside this presentation decision.
- Do not use `start_date` as a fallback event date or collapse it into `alert_date`.
- Do not show an alert GUID as a clickable BitSight alert link; no alert detail destination has been established.
- Do not imply complete history from a capped page. If completeness cannot be established, label the evidence as partial.
- Folder or subscription context belongs in the source register when it distinguishes monitored scope; it should not widen every row by default.
- Finding correlation and Jira create, append, edit, closure, and lifecycle interactions remain later work.
- The exported Jira ticket is working evidence, not a specification for the final ticket schema.

## Confidence

**0.84**

The observed BitSight UI and real payload shapes strongly support the typed single-column movement model and the event-date treatment. Confidence is below full because missing-date behavior, label conflicts, same-day ordering, and long Jira rendering have not yet been observed with representative production cases.
