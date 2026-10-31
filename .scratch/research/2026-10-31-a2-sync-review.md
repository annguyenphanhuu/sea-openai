# A2 integration review after branch synchronization

Date: 2026-10-31. Owner: An Nguyen. Scope: repository evidence, not external research.

## Revisions and verification

- `origin/main`: `1fd109e`; already an ancestor of `an-nguyen` before this review.
- A2 starting point: `06e27ea`, including fixed-window offline ETA validation.
- Huy: `0acf3ef`, demo scope and platform design; merged without conflicts.
- Truc: `6364e95`, A1 lifecycle/recovery design; merged without conflicts.
- Integration merge: `dc4ac62`. All fetched remote branch tips were ancestors of
  this commit. Local `main` was advanced to `origin/main`; remote main was not changed.
- `.venv/Scripts/python.exe -c "import contracts"`: exit 0.
- `.venv/Scripts/python.exe -m pytest -q`: **225 passed**, 6.49 seconds.
- `git diff --check`: exit 0. No runtime code changed in this review.

The incoming commits add specifications/research, not A3, an executor, an A1
runtime or HTTP routes. Passing the current suite does not verify those systems.
No release databases were opened or modified for this review.

## Integration findings, in priority order

### 1. A2 publication must follow the revised transaction boundary

Huy's platform design, sections 3 and 5, now commits completed A3 independently
of A2. A2 assessments, questions, progress, watermark and checkpoint publish
together. An A2 error keeps real current A3 results but fails the attempt and
denies proactive contact. The earlier A2 acceptance matrix incorrectly expected
health to roll back with A2; that planning document is updated in this unit.

Existing A2 APIs fit this composition: construct a fresh `ProgressTracker` from
committed records, apply it to `ReleaseAdapter(snapshot).orders()`, then call
`evaluate_tick`. `QuestionStore.save` does not commit. Discard the proposed
tracker on failure. The A2 CLI writes separate files and is not a transactional
platform coordinator. Huy implements the transaction; An writes cross-tests
against its real public APIs once available.

### 2. Version-bound order metadata is not specified in StoredTick

`logistics_an_nguyen/handoff.py::assessed_orders_payload` already exports
`created_at`, `handed_over_at`, reasons and provenance alongside assessments at
one cutoff. Huy's proposed `StoredTick` includes assessments/health/quarantined
IDs, but no metadata payload or clearly defined getter for these shipping dates.
`OrderAssessment` alone cannot supply them. This is a design gap to resolve with
Huy and Truc, not a demonstrated runtime defect.

Requested owner change: preserve `a2_order_list_v1` with the committed tick, or
specify an equivalent projection bound to the same version and sanitized source
snapshot. Call the exporter with the same eligible, non-cancelled order set used
by A2; raw quarantined orders would fail its exact-set validation. Never join
old assessments to newer source dates. Truc remains responsible for ownership
filtering and evidence redaction; the internal payload is not a public API.

### 3. A1 HTTP/auth ownership conflicts with the team plan

The A1 business spec's API section and harness section 4 say Huy mounts the
server and authenticates requests. `AGENTS.md`, `docs/team_plan.md`, and Huy's
latest design assign HTTP/auth/UI to Truc, with Huy providing Python platform
services and trusted execution context. Follow the repository ownership rule.
Truc should reconcile those A1 paragraphs before implementation. An should not
create an HTTP server or modify either owner's files to bridge the discrepancy.

### 4. Human eligibility review and A1 preconditions need alignment

Huy's demo design allows audited human evidence to resolve unknown responsibility
and force majeure without rewriting A2. The A1 spec currently requires A2
`fault_party` to be carrier/platform before proposing coins and rejects unknown.
A late order with unknown A2 fault but valid platform review could therefore be
blocked before reaching the executor. Keep the A2 assessment unchanged; Huy and
Truc need to agree how A1 consumes verified eligibility separately from logistics
facts. Unknown/unverified conditions must continue to deny grants.

Huy also specifies separate coins and voucher entitlements, with voucher requests
from source `rule`. The A1 spec describes coins but does not yet describe the
handoff to that rule. This is an integration dependency, not work for A2 or a
reason to add voucher decisions to the model.

## Work An can do next

1. Prepare the cross-owner integration cases in
   [the acceptance matrix](../specs/a2-platform-acceptance.md) and follow
   [the implementation plan](../plans/a2-platform-acceptance.md). Preparation is
   complete; executable platform tests wait for real APIs rather than fake success
   adapters, skipped tests or private schema assumptions.
2. Once Huy provides the first replay/A3/tick unit, prioritize one committed
   snapshot through existing A2 APIs, then A2-failure rollback, retry/restart,
   current-versus-historical guard and metadata consistency tests. This is the
   highest-value next implementation unit for An.
3. Continue offline ETA diagnostics independently if useful, using the existing
   fixed-window validation report and cohort breakdown. Do not promote the current
   risk probabilities to automated contact policy: the documented complete-case
   Brier is 0.1142 versus 0.0790 for always-on-time, and outcome censoring remains.
   Those are previously recorded results, not a rerun in this review.

No new A2 model, agent framework, dependency or shared contract is needed just
to consume the incoming documentation. The immediate missing implementation is
the platform integration, followed by A1 and HTTP/auth. Owner requests above are
recorded here for handoff; no messages or issues were sent to teammates.
