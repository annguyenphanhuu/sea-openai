# A2 UI handoff completion plan

1. Fetch origin and integrate main into `nguyen/a2-ui-handoff`.
2. Move `test_a2_history_regressions.py`, `test_a2_pipeline_verification.py`,
   `test_a2_state_composition.py`, `test_assessed_order_handoff.py` and
   `test_forecast_validation.py` into `acceptance_an_nguyen`.
3. Add source metadata projection and the five documented handoff fields;
   preserve existing assessment behavior and support minimal source schemas.
4. Export a representative 20-order sample from read-only release data and
   actual A3 health at one cutoff; record its provenance and field semantics.
5. Run focused handoff checks, contracts import, full pytest and diff checks.
   Fetch/merge any remote updates, then commit and push the verified unit.

## Verification

- Integrated `origin/main` at `91c9d46`; main remained unchanged at pre-push fetch.
- All five original test bodies preserved; handoff cases were appended.
- `.venv/Scripts/python.exe -m pytest -q acceptance_an_nguyen/test_assessed_order_handoff.py`:
  36 passed. Full `.venv/Scripts/python.exe -m pytest -q`: 534 passed in 13.27s.
- Imports of `contracts` and `logistics_an_nguyen` and `git diff --check` passed.
- Sample has 20 distinct orders: 10 COD / 10 PREPAID, spanning six observed
  statuses. Each evidence pointer resolves inside the exported envelope.
- Release core SHA-256 remained
  `65c820444b12bd644416f8d7688b1581ed9ef09f2bac5a1583168f63ec10f153`
  before and after read-only sample export. No source writes or ETA validation
  study were performed.
