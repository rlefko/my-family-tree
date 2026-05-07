# Conflict detection + resolution

Conflicts are surfaced by the rules engine at
`backend/src/my_family_tree/resolve/conflicts.py`. Each rule is a pure
function over the current DB state, idempotent, and produces stable IDs so
re-detection updates the existing row instead of duplicating.

## v1 rules

- **DateMismatch** — non-overlapping `[date_min, date_max]` for same `(subject, predicate)`.
- **PlaceMismatch** — different `place_id` for same `(subject, predicate)`, far apart.
- **ParentageMismatch** — multiple parents of same role; parent age outside plausible range.
- **DuplicatePerson** — dedup score >0.6 across distinct active persons.
- **SexMismatch** — `sex` claim conflicts with role in event.
- **ImpossibleAge** — events outside plausible lifespan.
- **CircularLineage** — parent-of cycles.
- **MultipleSpousesSameTime** — overlapping spouse_of date ranges (informational).

## Stable IDs

`stable_conflict_id(kind, sorted subject_ids, predicate)` returns a UUID
derived from a sha256 of the inputs so re-detection is an upsert.

## Resolution flow

User picks a `ConflictDecision` (`pick_a | pick_b | pick_neither |
merge_persons(loser_id) | both_true_different_subjects | needs_more_evidence`).
The choice is recorded as `proposal(action='resolve_conflict')`. On approval,
losing claims become `superseded`, the conflict is `resolved`, the canonical
entity is updated, and `fact_provenance` rows are written.

## Agent-assisted resolution

`resolve_conflict_with_agent(conflict_id)` spawns the conflict-resolver
subagent. It can read everything, search the web, and produce **one**
`resolve_conflict` proposal for the user to approve.
