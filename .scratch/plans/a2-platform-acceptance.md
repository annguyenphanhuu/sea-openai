# A2/platform integration acceptance plan

Owner: An Nguyen. Date: 2026-10-31.
Specification: [a2-platform-acceptance.md](../specs/a2-platform-acceptance.md).
Context: [branch synchronization review](../research/2026-10-31-a2-sync-review.md).
Status: preparation complete; executable platform acceptance awaits Huy's APIs.

## 1. Bind the first real platform unit

Fetch and integrate the team remote and main. Read the delivered public contracts,
migrations and entry points before naming test helpers. Keep changes in
`acceptance_huy/` and, only where A2 adaptation is needed, `logistics_an_nguyen/`.
Use a new `nguyen/platform-acceptance` feature branch for new implementation;
the current synchronization retains `an-nguyen` as explicitly requested.

Use tiny isolated source fixtures and runtime state under repository `runs/`
when exercising `QuestionStore`; it rejects persistent connections elsewhere.
In-memory state remains suitable for isolated transaction checks. Do not write
fixtures into release databases, use truth/heldout, or mock away A3/tick behavior
being asserted. Use separate connections for concurrency cases.

## 2. Verify publication before financial paths

- Establish a successful full snapshot through A3, ReleaseAdapter,
  ProgressTracker, evaluate_tick and QuestionStore. Assert literal status/date
  expectations and all committed row counts.
- Fail A2 after A3 has committed and after partial A2 writes. Assert actual A3
  remains current; assessments/questions/progress/watermark/checkpoint do not
  partially advance; the attempt fails and proactive gate denies.
- Retry the same tick and restart after a lost response. Assert stable receipts,
  no duplicate heartbeat/questions and no extra stationary interval.
- Race two NEXT calls, test skipped failed ticks, and inspect a consistent read
  view when the first A2 publication fails or only an older one exists.
- After Huy/Truc settle metadata persistence, assert one cutoff across assessment,
  created date, handover date and provenance, including quarantined-order handling.

## 3. Bind executor cases when delivered

Apply the existing acceptance matrix to real execution/evidence/review APIs.
Keep each rejection fixture otherwise eligible. Verify per-kind coins/voucher
uniqueness, authenticated sources, text provenance, source history, withdrawn
review heads, and transaction rollback. Do not infer money eligibility from A2
fault alone or make A2 write financial state.

## 4. Verification and handoff

Run import contracts, focused new tests, the full pytest suite and diff checks.
For failed platform assertions, report the minimal reproduction to Huy without
changing his implementation or weakening expected behavior. Record pending
integration accurately; absence of a module is not a passing acceptance test.
Commit and push each verified unit after fetching and merging fresh remote/main
updates. No main merge or push is part of this plan.
