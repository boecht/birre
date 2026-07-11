# BiRRe Real Alert Validation Decisions

## D1 - 2026-07-11 - Project Type

**Status quo:** The alert-to-Jira-action workflow has an approved brief, decomposed implementation plan, and implemented CLI/API core, but only fixture-based validation is currently visible.

**Decision to make:** Is the next discovery net-new work, an existing-feature/refactor, or uncertain?

**Options considered:**

- Net-new: begin a separate Jira or data-processing capability.
- Existing-feature/refactor: validate the implemented alert workflow against real BitSight behavior and use evidence to choose the next plan.
- Uncertain: research several possible roadmap branches without an anchor.

**Chosen:** Existing-feature/refactor.

**Rejected:** Net-new Jira setup and broad uncertain exploration, because real alert behavior is the highest-impact unresolved dependency for all downstream ticket work.

**Source inputs:**

- User selected real BitSight alert validation as the probable next direction.
- User confirmed new configured alerts are visible in the BitSight UI and offered authenticated browser comparison.
- Local code contains the implemented read-only `security-analyst-alerts` workflow.

## D2 - 2026-07-11 - Discovery Rigor

**Status quo:** This is a narrow real-data validation pass for an internal workflow whose output will later influence Jira company-watch tickets and lifecycle decisions.

**Decision to make:** How much evidence and challenge should the validation require?

**Options considered:**

- Scratch: one-off smoke test.
- Tool: focused API/UI comparison with a concise validation record.
- Shared: several representative alert shapes, explicit API/UI comparison, challenge checks, and a reusable research bridge.
- Production: formal review at every boundary.

**Chosen:** Shared.

**Rejected:** Scratch and Tool, because one successful response may conceal date-window, historical-alert, or schema gaps. Production is disproportionate for the current internal pre-production workflow.

**Source inputs:**

- User selected Shared rigor.
- The parent alert workflow was also shaped at Shared rigor because ticket classification and lifecycle decisions have operational consequences.

## D3 - 2026-07-11 - Finding Link Expectation

**Status quo:** BitSight alerts are event-table rows with no alert detail page. Findings are separate objects that may be opened, but the v2 alert payload does not directly expose a finding identity in the sampled risk-category shape.

**Decision to make:** Must every Jira company-watch action contain a direct BitSight finding link?

**Options considered:**

- Required for every ticket.
- Required only for finding-backed actionable events.
- Best effort when a stable correlation can be derived.
- Not needed initially.

**Chosen:** Best effort.

**Rejected:** Making the link a ticket-creation blocker, because alert events and rating/grade movement already provide useful company-watch evidence while stable finding correlation remains unproven.

**Source inputs:**

- User selected best-effort finding links.
- User confirmed alerts cannot be opened, while findings can.

## D4 - 2026-07-11 - First Useful Step and Preserved Promise

**Status quo:** Live evidence exposed several connected correctness gaps, while the larger alert-to-Jira workflow still includes ticket creation, updates, closure, and reporting.

**Decision to make:** What should the next useful delivery prove without silently replacing the larger product promise?

**Options considered:**

- Fix only one defect class, such as operation wiring or detail-field mapping.
- Validate a complete real-alert correctness bundle, then continue to Jira and lifecycle capabilities.
- Expand immediately into Jira connectivity or finding correlation.

**Chosen:** Validate the complete real-alert correctness bundle: generated alert-operation exposure/name, real start/end field normalization, before/after propagation into timeline evidence, category/risk-vector mapping for scoring, and bounded pagination/date-window proof.

**Rejected:** A single-defect repair, because it could produce plausible but incorrect Jira-shaped output. Immediate Jira or finding expansion is sequenced later because the deterministic action payload must first be trustworthy.

**Preserved remainder:** Live Jira lookup/create/append and issue results; existing-ticket updates; rating-recovery closure checks; due-ticket management summaries; broader category validation; and best-effort finding correlation.

**Source inputs:**

- User confirmed the corrected First Useful Step and expectation framing.
- Simplification, first-principles, and expectation-fidelity checks all supported separating immutable alert evidence from company-watch and Jira lifecycle state.
