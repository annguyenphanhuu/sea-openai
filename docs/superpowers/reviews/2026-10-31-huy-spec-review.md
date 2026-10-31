# Independent spec review — Huy platform, 2026-10-31

**Current final status: Approved after re-review.** The initial findings below are
preserved as review history; their resolution is recorded at the end.

## Spec Review

**Initial status: Issues Found**

Reviewed with a clean context, without the writer's rationale or a test-success
report. Scope: `2026-10-31-huy-platform-design.md`, workspace/repository
`AGENTS.md`, `docs/team_plan.md`, `docs/decisions.md`, actual shared types,
parameters/state schema, and the A2 replay/adapter/models/progress/service/question
interfaces. Applied the Superpowers spec-review criteria: completeness,
consistency, clarity, scope, YAGNI and readiness for implementation planning.

This is a design/interface review, not evidence that the proposed implementation
or release-wide financial eligibility works. No implementation or source data was
changed; no tests were run to substitute for the checks below.

## Issues that block approval

### 1. The Action cancellation path cannot return the data needed for confirmation

**Sections 4 and 6; lines 118–134, 177–186, 241–243.**

The spec explicitly supports `execute_action(cancel_request)` and says its caller
obtains workflow state through `list_order_actions` / the review queue. However:

- `execute_action` and `list_order_actions` return `ExecutionResult`, which has no
  `cancel_id`, `confirmation_id`, workflow status or version.
- `confirm_cancellation` requires `cancel_id`, `confirmation_id` and version.
- `list_review_queue` is the reviewer-facing API. Using it to recover a customer's
  awaiting-confirmation request would require giving that customer queue access,
  or defining an additional customer-scoped behavior that the spec does not have.

Consequently, a caller using the documented Action entry point cannot complete
the second step through the documented customer-facing APIs. The direct
`request_cancellation` return type does not fix the already-promised Action path;
the caller also needs a defined way to recover the existing request after restart
or a lost response without creating a different request.

**Required clarification:** expose an authorized lookup by action/cancellation ID
returning `CancellationResult`, or include a stable workflow reference and a
usable recovery path in the action result. Define whether action history reports
the immutable request receipt, current workflow state, or both. Keep review-queue
authorization separate from the customer's own cancellation lookup.

**Acceptance boundary:** request through `execute_action`, restart/lost response,
recover the same cancellation through a public customer-authorized API, confirm
it, and observe its later state. No direct SQL and no reviewer capability should
be needed by the customer.

### 2. There is no defined authority for `simulated_now` across mutations and restart

**Sections 3–6; lines 62–74, 157–175, 221–233.**

The design correctly rejects using `Action.requested_at` as the financial as-of
time, but then relies on `simulated_now` for freshness, future-message checks and
current source facts without defining where that clock comes from. `Platform`
has `start_at` and committed tick state, but no clock interface or rule declaring
which of them is authoritative between ticks or before the first tick. Restart
does not explicitly restore an authoritative decision time either.

The related mutation APIs accept `at`, `opened_at` and evidence `as_of`; the gate
selects historical health using `send_at`. Their relationship to the current run
time is unspecified. Section 7 explicitly bounds return-history reads by current
committed replay time, but no equivalent invariant governs these mutations.

Two plausible implementations therefore disagree: one freezes all decisions at
the last committed tick; another uses a caller-supplied time or a process clock.
They can reach different lateness, heartbeat and feed-freshness decisions for the
same persisted state. A backdated contact/control call could also select an old
healthy snapshot after the current feed has degraded unless the current-time
check is explicit. Trusted adapters still need this contract to avoid accidental
backdating and inconsistent recovery.

**Required clarification:** choose the server-owned simulated decision clock,
define its persistence/recovery and pre-first-tick behavior, and state which API
timestamps are event/audit timestamps versus authorized evaluation times. Define
how historical timestamps on mutation calls are validated against that clock;
historical queries must not implicitly authorize a current contact or release a
current control. No new TTL or wall-clock business policy is necessary.

**Acceptance boundary:** identical persisted state before/after process restart
gives the same decision time; older `requested_at`/`opened_at`/`at`/`as_of` cannot
select stale eligibility or bypass the current gate; future timestamps and
mutations before the first usable tick have explicit outcomes. Tests should
exercise times between ticks as well as committed tick timestamps.

## Recommendations (advisory, do not block approval)

- `QuestionStore` rejects persistent SQLite files outside repository `runs/`
  (`logistics_an_nguyen/questions.py`). Place file-backed tick integration and
  concurrency fixtures in a unique temporary directory under `runs/`, with
  cleanup, or limit ordinary temporary files to components that do not construct
  `QuestionStore`. Do not weaken the A2 guard to make fixtures work.
- The gate accepts caller-supplied `OrderFacts`. During planning, explicitly
  resolve or match the order and its required feeds against committed server
  facts before authorization. A shortened `required_feeds` tuple must not become
  a way to omit a degraded dependency. This follows the existing server-owned
  evidence requirement rather than adding a business rule.
- Keep the acknowledged FM-absence and historical non-coins mapping limitations
  visible in completion reports. A positive verified-fixture coins test must not
  be described as release-wide coins enablement. Fixture injection should remain
  a test seam rather than a client-accessible attestation path.

## Confirmed design alignment

- Ownership stays within Huy's modules/contracts/docs/configuration. A2 and A1/UI
  changes are not silently reassigned; the missing A1 integration is explicit.
- Integer coin arithmetic matches `contracts/params.py`: 5%, floor to thousands,
  minimum 10,000, maximum 1,000,000, with `None`/0 producing 10,000. Non-coins
  policies remain unconfigured and cannot write the coins ledger.
- A2's `ReplaySnapshot`, `ReleaseAdapter`, `ProgressTracker.records`,
  `evaluate_tick` and caller-owned `QuestionStore` transaction are usable seams
  for the proposed coordinator. Full snapshots and fresh per-attempt trackers
  avoid treating a delta as the complete A2 world or retaining rolled-back
  progress.
- Local-ledger atomicity, same-key conflicts, cross-command key namespace,
  once/order within one state authority, lost-response retries and the explicit
  absence of a cross-run wallet guarantee are coherent design constraints.
- Cancellation approval is honestly limited to a runtime workflow. A separate
  customer confirmation, snapshot/version checks and no automatic refund are
  retained; the blocking issue is access to its public workflow state.
- Return history distinguishes requests, distinct orders and physical returned
  scans, states coverage limits and preserves seller scope. It introduces no
  threshold, fraud verdict or automatic financial exclusion.

Resolve the two interface/time-authority gaps before writing the implementation
plan. The advisory items do not independently block approval.

## Re-review — revised specification

**Final status: Approved for implementation planning.**

Read the revised specification itself, including the new types, state fields,
clock contract, cancellation recovery and explicit-request seam. No writer
rationale or reported test success was used as evidence. No remaining concrete
planning blockers were found.

- **Original issue 1 resolved — sections 4 and 6:** `ExecutionResult.cancel_id`
  persists the workflow reference. `get_cancellation` returns current status,
  confirmation ID and version under customer-scoped `cancel:read` authorization.
  History/retries retain immutable request receipts, and the customer recovery
  sequence explicitly works without review-queue access or direct SQL. The new
  acceptance case covers Action request, lost response/restart, recovery and
  confirmation.
- **Original issue 2 resolved — section 3:** the last committed checkpoint is
  explicitly the decision clock, including between ticks and after restart.
  Pre-first-tick behavior is `run_not_ready`; caller timestamps cannot select the
  evaluation clock. Current gate/control checks use server now, evidence
  preparation requires that same now, and mutation transactions re-read the
  checkpoint/version before committing. Boundary cases cover backdated/future
  timestamps and unchanged decisions between ticks.
- **Advisories addressed — sections 3–5 and 8:** file-backed QuestionStore tests
  remain under `runs/`; the gate now accepts only order ID and resolves committed
  feed dependencies; release-wide coins enablement remains explicitly blocked
  pending approved evidence/policy. The new shared feed DTO avoids importing A2
  into contracts at runtime and maps explicitly to A2's existing FeedHealth.
- **New request-signal seam is consistent — sections 4–6:** startup supplies a
  deterministic, versioned A1 rule. Only the service can mint the persisted
  signal from an authenticated, correctly bound text message in an A1-opened
  chat. Missing/negative rules mint no signal; rule errors roll back. Voice and
  client-provided request codes cannot manufacture provenance. Order-only
  cancellation evidence is explicitly permitted and cannot qualify for coins.

Approval covers the design's readiness for planning, not implementation success.
The frozen simulated clock means adapters must honor replay time; wall-clock
events ahead of the committed tick are explicitly rejected. This is a stated
design choice, not an unspecified time policy.

Force-majeure **unknown still means no grant**. An optional future user answer
does not change that rule. A1 integration, verified FM-absence evidence and
historical non-coins mapping remain named dependencies; approved cancellation
still means only a runtime workflow. Coins arithmetic, ownership boundaries and
the prohibition on return-history thresholds/fraud verdicts/financial exclusion
remain intact. Implementation tests and independent implementation review are
still required.
