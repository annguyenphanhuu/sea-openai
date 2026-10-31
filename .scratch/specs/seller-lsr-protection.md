# A2 seller LSR protection

Implement the requested seller protection on `nguyen/seller-lsr-protection`.
Keep shared `FaultParty`, `OrderAssessment`, dependencies and UI/API code unchanged.

- Read the static release `policy` row `seller_prepare_days` (currently `2`)
  through the read-only reader. Missing policy stays unknown; invalid values fail
  validation. The separate `seller_handover_days=3` cancellation rule is not used.
- For every assessment with `late_days > 0`, compare the earliest visible
  `handed_over.event_at` minus `orders.created_at` with the policy duration.
  Exactly 48 hours is on time when the policy is 2 days. Do not round to dates.
- Require both event and ingestion at/before the tick. Keep order, scan and policy
  provenance in assessment evidence. Missing scans/policy, unavailable feeds and
  conflicts produce an unknown result, never seller blame or an exemption.
- On-time handover plus actual lateness attributes otherwise unknown fault to
  `carrier`. Preserve explicit customer, platform and force-majeure fault and all
  existing status priority rules. Driver text cannot change this determination.
- Add `handover_on_time: bool | null`, `fault_owner` (an alias of `fault_party`),
  and `lsr_exemption: str | null` to both assessment and order-list payloads.
  Emit the Vietnamese "Miễn trừ LSR" explanation only for the supported carrier
  case. This is an A2 recommendation with evidence, not a persisted penalty change.
- Older custom snapshots can omit the optional policy field. They keep their
  existing fault behavior and do not silently assume a two-day policy.
- Verify boundary times, replay cutoff, duplicates, delivery completion, invalid
  inputs, feed gates and competing fault evidence using isolated fixtures.
  New regression tests live in An Nguyen's `acceptance_huy/` folder.

The review's 444/619 statistic is context supplied by the user, not a rule or a
hard-coded expected count; any release validation must state its own cutoff.
