# A2 UI handoff completion

Requested on 2026-10-31: finish the UI handoff before further ETA validation.
The review identifies missing handoff fields and misplaced tests, not a new
assessment defect. Keep the shared contract and assessment rules unchanged.

- Extend each `a2_order_list_v1.orders` item with `customer_id`, `payment`,
  `priority`, `cause`, and `evidence_ref`.
- Read customer ID and payment method from visible source orders only. Payment
  is `COD` or `PREPAID`, not a settlement status, quote or executable amount.
  Missing metadata or unusable orders feed produces null display values.
- Priority is the 1-based rank in `contracts.types.STATUSES`, lower first.
  Cause contains the unchanged assessed `fault_party` and `reason_codes`.
  It does not invent a verified root cause from source free text.
- Evidence reference is a JSON Pointer to that item's assessment evidence in
  the same envelope. It is not a durable platform Action evidence reference.
- Commit 20 actual, as-of release assessments as
  `logistics_an_nguyen/sample_orders.json`, with source/cutoff provenance.
  Use actual A3-computed health; never synthesize healthy release feeds or data.
- Move the five A2 files out of `acceptance_huy` to `acceptance_an_nguyen`, as
  explicitly requested. Preserve their assertions and add handoff regression
  cases. Contracts, other owners' implementation and source DBs stay untouched.

Verify projection, metadata trust, cause/priority fidelity and reference
resolution; run the full existing test suite and source hash checks. No new
ETA quality study is part of this work.
