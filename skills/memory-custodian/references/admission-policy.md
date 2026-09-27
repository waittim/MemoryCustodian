# Admission Policy

Protocol 0.8 / Entry schema 3 active durable memory MUST have a stable Entry
ID, `Status: active`, a valid Scope, Evidence, and a matching typed body.
Decisions, constraints, rejections, and area hard-memory entries MUST also
have an active Subject ID and controlled Facet. `MC-TOMB` is a topic-free
erasure guard; `MC-AREA` rule/profile entries are workflow inputs. Neither
class is a structural owner, and neither requires Subject/Facet. See
`memory-file-protocol.md` for the normative Entry contract.

Agent inference, code observations, tentative conclusions, and unconfirmed conversation content MUST remain
in `inbox.md` as candidates. Candidate promotion MUST be explicit: confirm the claim or cite an authoritative project
source, create a new formal Entry ID, and preserve the candidate-to-entry audit link.

For active structured entries, normalized `Scope + Subject ID + Facet` is the exact owner key. A duplicate owner
is a conflict; use explicit supersession, an auditable exception/reconciliation record, or a previewed Subject
merge. Similar text, aliases, timestamps, and display names do not prove identity or precedence.
