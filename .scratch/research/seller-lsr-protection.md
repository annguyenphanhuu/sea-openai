# Seller LSR protection validation — 2026-10-31

Implementation branch: `nguyen/seller-lsr-protection`.

## Source inspection

Read-only `core_14d.sqlite` contains the static policy row
`seller_prepare_days="2"`; the distinct `seller_handover_days="3"` row belongs
to cancellation. Policy has no ingestion or effective-date columns. The optional
A2 projection preserves missing policy as unknown rather than inventing defaults.

## Release check

Cutoff: **2026-10-28 12:00:00 Asia/Ho_Chi_Minh**, the release simulation clock
and the existing sample cutoff. Feed health came from the actual
`platform_huy.sysguard.health_for` output over the visible snapshot. All three
required feeds were usable. No simulated heartbeat or contact authority was added.

| Measure | Count |
| --- | ---: |
| Assessed, non-cancelled orders | 10,193 |
| Orders with actual `late_days > 0`, including higher-priority statuses | 676 |
| Evidence-backed carrier/LSR exemption recommendations | 351 |
| `seller_self` orders with actual lateness | 314 |
| These seller-self orders with on-time handover | 290 |
| These seller-self orders receiving the carrier-rule exemption | 144 |
| Existing sample IDs retained | 20 |
| Sample orders with an exemption explanation | 7 |

On-time handover does not overwrite a confirmed customer, platform or
force-majeure cause. This explains why the on-time count and carrier-rule exemption
count differ. The review's **444/619** figure was not reproduced at this cutoff;
its population/cutoff were not supplied and are not hard-coded into the feature.

The refreshed sample preserves every selected order ID, status, late-day count,
late probability and ETA. Example `2610182F1K1SGO`: created at
`2026-10-18T10:20:12Z`, handed over at `2026-10-19T07:17:26Z`, classified late;
the new payload has `handover_on_time=true`, `fault_owner="carrier"` and the
Vietnamese exemption explanation. Full source and derived evidence is included.

Core SHA-256 before/after was identical:
`65c820444b12bd644416f8d7688b1581ed9ef09f2bac5a1583168f63ec10f153`.
Local validation artifacts are ignored under `runs/seller-lsr-protection/`.

## Automated checks

- Baseline before implementation: `python -m pytest -q` — 633 passed.
- Final regression suite: `python -m pytest -q` — 694 passed, including 61 new
  seller-protection cases in the An-owned acceptance folder.
- Existing sample consumer: `node --test logistics_an_nguyen/ui/data.test.mjs`
  — 9 passed after refreshing the sample.
- `python -c "import contracts"` and `git diff --check` passed.
- Refetched origin and merged `origin/main` before committing; already current.

## Scope

Shared contracts/dependencies and other owners' tests/UI/API were not edited.
This change emits A2 facts and a reviewable recommendation. It does not execute a
penalty exemption, contact, payment or other external business effect.

## Follow-up integration with main

At the user's request, integrated `origin/main` at `4e71562` into the feature
branch. Git merged without textual conflicts. Integration checks identified:

- The demo checkpoint loader passed additive `fault_owner`, `handover_on_time`
  and `lsr_exemption` export fields into `OrderAssessment`, breaking restart.
  The loader now reconstructs exactly the shared dataclass fields. Saved payloads
  and order-list metadata retain all LSR information; shared contracts stay intact.
- An-owned release integration tests expected unknown fault for demo order
  `261021ZS7E76FW`. Its timely scan now supports carrier attribution. Expectations
  include the handover/exemption proof, while unreviewed coin requests must still
  return `coins_evidence_unavailable` with an empty ledger. Staff review must not
  mutate the exported A2 order.
- Main's A1 test `test_local_reservation_refuses_new_message_and_durable_evidence`
  still inspected the former synchronous harness store. It now inspects the raw
  runtime SQLite store, matching existing harness tests. No business assertion
  or storage deadline requirement was removed.

The necessary cross-module follow-up is limited to the checkpoint loader and
that one test call. Added restart coverage checks old and extended checkpoint
shapes, exact assessment/order restoration, and the persisted incomplete A1 phase.

Final merged verification:

- `python -X utf8 -m pytest -q --tb=short`: **770 passed** (151.80 seconds),
  including real-release ticks, HTTP presenter checks and both checkpoint shapes.
- `python -X utf8 -m pytest -q care_truc/tests`: **501 passed**.
- `node --test logistics_an_nguyen/ui/data.test.mjs`: **9 passed**.
- Focused affected end-to-end cases: **5 passed** before the full acceptance run.
- Contract import, staged diff check and `python scripts/guardrails.py --all` passed.
