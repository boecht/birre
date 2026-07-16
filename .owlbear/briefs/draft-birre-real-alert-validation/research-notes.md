# BiRRe Real Alert Validation Research Notes

## Verified Findings

- The focused workflow and CLI tests pass: 15 tests across `test_security_analyst_workflow.py` and `test_cli_app_commands.py`.
- The production CLI command is `security-analyst-alerts`; it performs read-only v2 alert retrieval and v1 company retrieval.
- The first bounded production run failed before retrieving alert data because the workflow calls v2 tool `getAlerts`, which is not present in the generated FastMCP server.
- The bundled v2 OpenAPI schema declares `GET /alerts` with operation ID `AlertsList`. Local generated-tool inventory confirms `AlertsList`, `CustomerAlertsList`, and `LatestAlertsList`.
- The `security_analyst` context creates the v2 server but applies an allowlist containing only risk-manager company-request tools. That allowlist hides all alert tools, including `AlertsList`.
- Fixture-based tests do not currently prove that the workflow's endpoint constant matches generated OpenAPI tool names or that the security-analyst v2 allowlist exposes the required operation.
- With those two local wiring defects bypassed in memory, a bounded read-only production call succeeded against BitSight.
- The first page contained more results and distinct companies than the 20-alert / 10-company sample could retain, producing both `alert_page_cap_reached` and `company_cap_reached`. The sample is representative evidence, not a completeness check.
- All 10 retained alerts had `alert_date` 2026-07-09 despite an `alert_date_gte=2026-07-01` lower bound. This is consistent with lower-bound filtering for the sample, but does not yet prove behavior for older retained alerts or subsequent pages.
- The sample alert-type distribution was 8 `RISK_CATEGORY`, 1 `RATING_CHANGE`, and 1 `RATING_THRESHOLD`.
- Real rating-alert details use `start_rating` and `end_rating`; threshold alerts additionally use `rating_threshold`.
- Real risk-category details use `start_grade`, `end_grade`, `threshold_grade`, and `risk_vector`.
- The implemented movement parser expects `rating_before` / `rating_after` or `category_before` / `category_after`, so it does not derive alert-specific movement from the real detail fields.
- Company enrichment nevertheless supplied current rating and rating history for all 10 retained companies, and the workflow derived a rating drop from `company_history` for each action item.
- The final Jira body currently leaves `rating_before` and `rating_after` empty even when a real alert contains start/end values. Movement calculation returns only drop and source, and workflow payload construction reads before/after from normalized top-level fields that are never populated from `details`.
- Priority category matching is also misaligned: real `alert_type` values are API enums such as `RISK_CATEGORY`, while the scoring table expects human event/risk-vector labels such as `botnet infection` and `open ports`.
- User-provided UI evidence shows the BitSight Alerts view as a 2,081-row historical table sorted by date. Alerts cannot be opened into a separate detail view; findings can be opened separately.
- The visible alert table columns are Date, Company, Category, Alert, and Tier / Folder / Subscription.
- The UI renders numeric rating events directly as start rating to end rating, for example `630 -> 620`, and grade events as start grade to end grade, for example `C -> D` or `B -> C`.
- The UI category presentation distinguishes threshold/rating events from risk-vector labels. Visible examples include SSL Configurations, Web Application Security, and Open Ports.
- This UI behavior maps directly to the real API detail shapes: `start_rating` / `end_rating` for numeric events and `start_grade` / `end_grade` plus `risk_vector` for risk-category events.
- The alert table is an event log rather than a lifecycle object list. Older alerts remaining visible does not by itself imply that the API lower-bound filter is broken.
- A user-run direct v2 query for `RISK_CATEGORY` alerts with `alert_date_gte=2026-07-09`, `expand=details`, and `limit=10` reported 83 matching alerts and a valid next-page offset.
- In the user-provided response shape, `trigger` is already the human risk-vector label and matches `details.risk_vector`; `alert_type` remains the envelope enum `RISK_CATEGORY`.
- The response confirms the one-day event distinction: `alert_date` is 2026-07-09 while `start_date` is 2026-07-08 in the shown sample.
- An authorization value appeared in the manually shared request. It was not copied into project artifacts, decoded, or reused. Future live calls should continue to rely only on locally configured credentials.
- User-authorized direct read-only calls using the locally configured credential sampled three documented envelope types from 2026-07-01 with `expand=details` and a three-record limit per type. Only non-identifying aggregate and field-shape evidence was emitted.
- `RISK_CATEGORY` reported 239 matches and a next page. All three sampled records used detail keys `start_grade`, `end_grade`, `threshold_grade`, and `risk_vector`; observed human labels included Web Application Security and Patching Cadence.
- `RATING_THRESHOLD` reported 43 matches and a next page. All three sampled records used detail keys `start_rating`, `end_rating`, and `rating_threshold`; the human trigger was Threshold.
- `PERCENT_CHANGE` reported 847 matches and a next page. All three sampled records used detail keys `start_rating`, `end_rating`, and `rating_change_pct`; the human trigger was Percent Change.
- The bundled OpenAPI enum includes `PERCENT_CHANGE` but omits `RATING_CHANGE`; production nevertheless accepts `alert_type=RATING_CHANGE` and returns that envelope. The bundled schema is therefore incomplete or stale relative to production and cannot be the sole authority for supported alert types.
- The sampled `RISK_CATEGORY` and `RATING_THRESHOLD` records had `alert_date` 2026-07-09 and `start_date` 2026-07-08. The sampled `PERCENT_CHANGE` records had `alert_date` 2026-07-07 and `start_date` 2026-07-06.
- A direct `RATING_CHANGE` query from 2026-07-01 reported 13 matches and a next page. Five sampled records consistently used `start_rating` and `end_rating`, with `trigger=RATING_CHANGE`.
- The first 100 unfiltered alerts from the same lower-bound window reported 1,179 total matches and contained 81 `RISK_CATEGORY`, 8 `RATING_CHANGE`, and 11 `RATING_THRESHOLD` records. This first-page distribution does not establish the complete type set; the separately filtered `PERCENT_CHANGE` query proves that type also exists in the window.
- Alert movement is polymorphic by envelope: `RISK_CATEGORY` carries grade movement; `RATING_CHANGE` carries rating endpoints; `RATING_THRESHOLD` carries rating endpoints plus threshold; `PERCENT_CHANGE` carries rating endpoints plus percentage change.
- `prozess.htm` defines incoming score changes and findings as inputs to operator assessment. Its priority matrix combines partner tier, exhaustive Annex A event category, score correction, and expert correction factor; the operator's expert judgment sets final priority.
- `operative_043905.html` defines score drops of at least 20 points and threshold crossings as assessment triggers, except when caused exclusively by Annex A `N/A` categories. Annex A `-1` and `0` categories also independently trigger assessment.
- The operative ticket table is explicitly non-normative and uses date, score change, category/type, action, and link as adaptable evidence fields.

## Candidate Implications

- Live API validation requires two small implementation corrections or an equivalent test-only bypass: call the generated `AlertsList` operation and expose it in the `security_analyst` context.
- A generated-tool inventory assertion would catch future workflow/OpenAPI naming and visibility mismatches earlier.
- The local wiring findings and real payload findings are distinct: wiring blocks the normal production path, while the bypassed bounded call established the payload shape needed for normalization.
- The real payload appears sufficient to derive rating and grade movement after explicit field mapping; another BitSight endpoint is not yet justified for that narrow purpose.
- Risk-category scoring likely needs to use normalized `details.risk_vector`, while `alert_type` should remain the event envelope type.
- `trigger` is a simpler verified source for the human category, with `details.risk_vector` available as cross-check/source evidence for risk-category alerts.
- The non-final Jira timeline can be built from alert dates plus normalized start/end rating or grade evidence, augmented by company history. The UI comparison confirmed the intended movement interpretation and category labels.
- A Jira change-over-time row should represent the displayed event semantics: date, normalized risk-vector/category label, start/end rating or grade, and derived numeric change where meaningful. Alert GUID remains provenance rather than a user-facing object link.
- Finding links are a separate enrichment/correlation concern because BitSight does not expose an alert detail page.
- The simplification check recommends separating access-wiring defects from schema evidence while sequencing them into one bounded correctness proof; finding correlation, Jira integration, exhaustive historical analysis, and later lifecycle work remain follow-ups.
- The first-principles check distinguishes immutable alert evidence from long-lived company watches and Jira lifecycle state. Alert movement can justify timeline evidence, but does not by itself prove causality, ownership, remediation state, or that every event warrants a ticket.
- The expectation-fidelity check rejected the earlier single-follow-up framing because several correctness defects are non-substitutable. Real-schema repair must not replace the larger promise of correct Jira-action data and eventual live Jira results.
- Sample acquisition can remain simple: make bounded direct API calls, retain sanitized structurally faithful examples, and state the observed coverage. No separate candidate/certified fixture lifecycle is justified.
- Production observations override contradictory bundled-schema assumptions, while the bundled schema remains useful for initial query and field hypotheses.
- Rating-only alerts do not need an invented risk-vector category to enter assessment. They can carry a provisional partial priority calculation until exhaustive Annex A classification or operator judgment supplies the missing category component.

## Open Research Questions

- Does `alert_date_gte` remain a reliable inclusive lower bound across later pages and repeated runs, independent of older rows retained in the UI event log?
- How should numeric rating events and letter-grade risk-vector events coexist in one Jira change-over-time table without implying false numeric equivalence?
- Which real category variants and casing rules must be normalized before priority scoring is trustworthy beyond the sampled `RISK_CATEGORY`, `RATING_CHANGE`, and `RATING_THRESHOLD` envelopes?
- How does a user navigate from a company or risk vector to the relevant finding when alerts themselves cannot be opened?
- Which finding identity and URL parameters are stable enough to place in Jira: risk-vector-filtered finding list, rolled-up observation ID, or another finding GUID?
- For which finding-backed categories is best-effort correlation useful enough to pursue after the correctness bundle?
