# Admission Policy

Protocol 0.7 admits active durable memory only when the entry has a stable Entry ID, `Status: active`, a valid
scope, a typed body, and at least one `user-confirmed` or source-backed Evidence item. Decisions, constraints,
rejections, and area entries also require an active Subject ID and controlled Facet.

Agent inference, code observations, tentative conclusions, and unconfirmed conversation content belong in
`inbox.md` as candidates. Candidate promotion is explicit: confirm the claim or cite an authoritative project
source, create a new formal Entry ID, and preserve the candidate-to-entry audit link.

For active structured entries, normalized `Scope + Subject ID + Facet` is the exact owner key. A duplicate owner
is a conflict; use explicit supersession, an auditable exception/reconciliation record, or a previewed Subject
merge. Similar text, aliases, timestamps, and display names do not prove identity or precedence.
