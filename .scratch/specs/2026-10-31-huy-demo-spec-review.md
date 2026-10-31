# Independent demo spec review — 2026-10-31

## Spec Review

**Status: Issues Found**

Reviewed the full `.scratch/specs/2026-10-31-huy-platform-design.md` against the workspace/repository instructions, current demo decision log, `docs/decisions.md`, `docs/team_plan.md`, the actual v0 contracts/state schema, and A2's adapter, replay, models, assessment, progress, service and QuestionStore interfaces. Also read the orchestration research and release demo candidates. Applied the Superpowers `brainstorming/spec-document-reviewer-prompt.md` checklist in a fresh review context, without relying on a previous approval or an implementer's report.

This is a design review, not verification of an implementation. No code, tests, source databases, Git state or other files were changed.

### Issues that block planning the affected behavior

1. **Sections 5–6 and 9: superseding human decisions do not have defined execution-time invalidation semantics.** Section 9 selects the latest *verified* fields matching source/material fingerprints; the review table has immutable decisions but no supersession/revocation marker or deterministic revision ordering. Section 6 rechecks source facts, current assessment and freshness, but does not explicitly re-resolve the human decisions behind an already prepared evidence ID. At one frozen simulation time, an operator can record FM absent, prepare evidence, then record a newer FM present/unknown decision without changing source rows or the A2 assessment. The old evidence still satisfies the written assessment/as-of/source-fingerprint requirements. Searching only for verified fields can also fall back to an older absent decision after a newer unknown decision. These interpretations produce different grant outcomes.

   Define whether a new review replaces all fields or only explicitly supplied fields, how a human withdraws a prior clearance, and how equal-business-time reviews are ordered. Bind evidence to the selected review revisions and revalidate their current authority inside the execution transaction; an existing successful receipt must still replay unchanged. Include a case where review changes after evidence preparation and before the first grant, with no NEXT tick, plus a case where one benefit has committed and clearance is withdrawn before the other. This needs no TTL, provider or change to the confirmed eligibility rules.

2. **Sections 3–4 and 9: the public read contract cannot return independently committed current A3 health after A2 failure.** Section 3 intentionally commits A3 heartbeat/health before A2 and retains those rows when A2 fails. However, `CommittedView` contains health only indirectly through `latest_tick: StoredTick`, whose health belongs to the last successfully published A2 batch. `TickAttempt.a3_status` and error codes cannot carry the actual newer feed timestamps/statuses or heartbeat. For example, A3 at T+30 completes and A2 fails: the advertised read view either exposes T health or must silently change the meaning of the historical `StoredTick`. Before the first A2 success it has no health payload at all. This prevents the stated guard/degraded-state handoff from being implemented faithfully through the listed APIs.

   Add an explicitly timestamped current A3 snapshot to the view, or a separate authorized guard-health getter, while preserving the assessment's original health/as-of in `StoredTick`. Specify the pending/failed/no-A3-result case and expose the current effective proactive decision/control separately from historical health. Verify A3-completed/A2-failed both before the first publication and after a successful earlier tick. Trúc can then build the guard UI/API without inventing a direct SQL integration or displaying old health as current.

### Recommendations — advisory, do not block approval

- Make the stored evidence shape explicitly per-kind for source-history classification and references. Sections 6 and 9 correctly require independent coin/voucher history, but section 5 currently names a single `history_classification`; a mapping avoids an implementer accidentally applying one scalar to both actions. Preserve live local-ledger checks outside review fingerprints.
- In the implementation plan, document the accepted evidence-reference namespace/resolver, each review field's material dependencies, and an example of a real human verification note tied to the release candidate. The spec correctly assigns substantive verification to the human and does not infer FM absence from a delivered scan or from missing alerts. A technically valid review record alone must not be presented as proof that the candidate has already been verified.
- Keep Trúc's real deterministic request adapter, authenticated transport origin, separate cancellation confirmation turn and handoff persistence as explicit integration dependencies. Their absence does not prevent Huy from completing the specified Python foundation, and fixture adapters do not establish the real positive end-to-end demo.

### Supported design conclusions

The existing A2 interfaces support the proposed safe projection, full-snapshot evaluation, fresh ProgressTracker per attempt and atomic QuestionStore persistence without editing An's modules. The clock/attempt transaction, separate completed-A3 commit, atomic A2 checkpoint publication, sticky proactive denial and retry-count publication guard provide a coherent crash/retry design. The spec retains D1–D5, fixed +30-minute NEXT, immediate chat at simulation time, wall-time audit, read-only sources and explicit ownership boundaries.

The local coin/voucher ledgers, permission matrix, amounts, independent once-per-kind/order checks and immutable receipts match the confirmed internal demo scope. Return-history counts stay descriptive and seller-scoped; no fraud inference, provider effects, voucher redemption or expiry policy is added. These conclusions are based on document/code inspection and do not certify runtime correctness or test results.

## Re-review of revised spec — 2026-10-31

**Final status: Approved for implementation planning.**

Read the revised spec directly, including the new public DTOs/APIs, schema additions, execution transaction order, acceptance cases and review dependency rules. This re-review addresses the two original blockers and related advisories; the initial findings above remain as the review history. No remaining implementation-blocking ambiguity was found within that scope.

1. **Human review supersession: resolved.** Sections 4, 5, 6 and 9 now provide an authorized revision getter, optimistic `expected_revision`, immutable integer revisions with `UNIQUE(order_id, revision)`, full replacement of all four fields, and an explicit withdrawal operation. The head remains authoritative even when unknown, withdrawn or invalid; there is no fallback to older verified fields. Prepared evidence binds the head ID/revision, and a first execution rechecks that head under the same `BEGIN IMMEDIATE` transaction as the grant. Review writes use the same SQLite writer serialization. Existing receipts replay before eligibility/review re-evaluation, preserving previously committed results without authorizing a new grant. Section 8 explicitly covers a same-clock withdrawal after preparation and withdrawal between the two separate benefits. These changes resolve both ordering and stale-clearance behavior without adding TTL or changing eligibility.

2. **Independent current A3 read state: resolved.** `GuardHeartbeatRecord` and `CurrentGuard` now expose actual current-attempt heartbeat/feed state, current sticky control and an effective gate independently of `StoredTick`. The spec defines completed-A3/A2-failed, first-attempt failure, and pending/failed/missing-A3 cases. Historical `StoredTick.feed_health` retains its publication meaning. Clock, attempt, A2 snapshot and current guard are read in one SQLite transaction, with explicit `state:read` access and own-order filtering. Section 8 covers the failure and concurrent-read cases. Trúc can consume this contract without inventing a newer health payload inside a historical A2 result.

The related advisories are also addressed: evidence has separate `history_by_kind` entries; the allowlisted resolver and review field dependencies are documented; runtime ledgers remain live checks outside review fingerprints. The positive release candidate explicitly still requires a real human verification note and real A1/transport integration. Those outstanding demo inputs are accurately described dependencies, not claims of completed verification and not blockers to planning Huy's foundation.

Only this review file was appended. No implementation, test execution, database mutation or Git operation was performed. Approval establishes readiness for the implementation plan, not runtime correctness or end-to-end demo completion.
