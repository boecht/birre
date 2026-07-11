# First-Principles Stance

## Irreducible Core

The observed need is narrower than “validate the alert-to-Jira workflow”: establish whether BitSight exposes trustworthy, bounded evidence of company rating or risk-vector changes, with stable event and company identity, sufficient for a human to recognize what changed and when. Real-data validation can prove that evidence claim. It cannot by itself prove that every qualifying event should create or update a Jira company-watch ticket.

## Strongest Challenges

### Jira tickets are an unproven operational outcome

The reference brief inherits company-watch tickets as the unit of work, but the current observations establish only that BitSight has a historical alert table and that Jira ticket evidence is desired. They do not establish who acts on a ticket, which decision it enables, whether one ticket per company is correct, or which events merit action rather than provenance only. Treat ticket production and lifecycle as a downstream hypothesis, not an outcome validated by matching API data to the UI.

### Immutable events and company watches have different identity and lifecycle

An alert is an immutable occurrence with its own date, movement, category, and provenance. A company watch is a potentially long-lived operational concern that may aggregate many events and periods without sharing their lifecycle. Company identity is a plausible grouping key, but the evidence does not make an alert, a company watch, and a Jira ticket interchangeable. Validation should preserve these distinctions rather than interpreting old visible alerts as active work or ticket state.

### Timeline evidence is necessary but not sufficient for action

The API/UI observations support a defensible event timeline: event date, company, risk-vector or rating category, and start/end rating or grade. Company rating history may corroborate or contextualize that timeline, but it is a different evidence source and must not silently replace alert-specific movement. A reconstructed timeline can show what changed; it does not establish causality, current remediation need, priority, ownership, or ticket lifecycle.

### Finding links are enrichment, not part of alert validity

Alerts have no observed detail destination, and sampled alerts do not expose a proven stable finding identity. Findings are separate, navigable objects. A best-effort finding link may add investigative value when correlation is defensible, but its absence does not invalidate an alert event, timeline evidence, or a company-watch concern. Conversely, a loosely correlated finding link must not be presented as provenance for the alert.

### Completeness is not yet the right proof target

The bounded sample can test schema fidelity, identity, movement semantics, pagination behavior, and lower-bound behavior. It cannot demonstrate complete historical capture, explain every older UI row, or validate all alert categories. Those broader claims are unnecessary unless a concrete user decision depends on exhaustive history rather than trustworthy bounded evidence.

## Framing Test

The discovery is the right next problem only if its claimed outcome is reduced to proving the fidelity and limits of BitSight event evidence. It is not sufficient evidence for approving Jira creation, prioritization, update, or closure behavior. Those outcomes require observed operational needs beyond the current API/UI comparison and non-final ticket artifact.

## Confidence

**0.91.** The API/UI evidence strongly supports the event-versus-work-item distinction. Confidence is lower only on the exact Jira need because no direct observation of Jira consumers, decisions, or lifecycle behavior is present in the discovery record.
