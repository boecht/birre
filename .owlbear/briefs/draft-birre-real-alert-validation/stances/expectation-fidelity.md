# Expectation-Fidelity Critique

## Material Challenges

- The earlier goal of selecting a single follow-up area would silently descope the work. Real evidence already shows multiple non-substitutable correctness gaps: generated operation naming, tool visibility, start/end field normalization, before/after propagation, and category scoring.
- Repairing only schema mapping could make the Jira-action payload look complete while leaving priority calculation or production wiring wrong.
- The change-over-time timeline is not fully validated merely because company-history fallback produces a drop. Alert-derived start/end values and labels must survive into caller-facing evidence.
- The First Useful Step must name the remaining product promise: live Jira create/append results, existing-ticket updates, closure checks, due-ticket summaries, and best-effort finding correlation.
- Real-data priority correctness remains unproven across the broader category set, including the existing Web Application Security ambiguity.

## Required Fidelity Correction

Treat real-alert validation and the inseparable correctness gaps it reveals as one bounded outcome. Do not require discovery to select only one defect class. Keep validation completion distinct from delivery of the full alert-to-Jira workflow.

## Done-but-wrong Version to Avoid

A command that successfully returns Jira-shaped JSON from real alerts but:

- depends on a test-only wiring bypass;
- omits alert start/end movement from the Jira timeline;
- scores API envelope types instead of human risk-vector categories;
- treats one sampled page as proof of date and pagination behavior; or
- presents the repaired payload as completion of live Jira workflow delivery.
