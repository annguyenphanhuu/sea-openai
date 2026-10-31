# Integrated local demo

Run from the repository root with Python 3.11 and the shared requirements installed:

```powershell
python -m platform_huy.serve_ui --integrated --port 8765
```

Open `http://127.0.0.1:8765/`. The source release is read from `SEA_RELEASE_DIR`
or `data/release_main`. Both `core_14d.sqlite` and `ops_14d.sqlite` are required.
Runtime writes go to `runs/integrated-demo/state.sqlite` and its sibling A1 store.
Use `--state-path runs/demo-new/state.sqlite` for a separate clean demonstration.
Source databases are opened read-only; customer text and grants are runtime records.

## Walkthrough

1. Press NEXT. Replay advances from October 24, 2026 at 14:00 to 14:30 Vietnam time.
   A3 checks feeds, A2 assesses visible orders, then A1 processes eligible contacts.
   The page shows phase timings, status counts, a contact queue and open chats.
2. Select `261021ZS7E76FW`: real synthetic-release COD order, items value 525,000 VND,
   guaranteed date October 22. The formula quotes 26,000 xu.
3. Inspect the order evidence. Huy must personally complete the staff verification
   fields, select relevant evidence and record a reason. Source data alone does
   not establish force-majeure absence; the demo never pre-approves this decision.
4. In the A1-opened chat, ask why the order is late, then type `Tôi xin xu`.
   A successful local grant appears in the ledger under `xu:261021ZS7E76FW`.
   Record buttons expose the stored outbox/ledger entries. No Shopee wallet is used.
5. Type `Tôi muốn hủy đơn`, then use the confirmation button. The executor queues
   a request requiring approval; it does not cancel the source order or refund money.
6. Type `Tôi muốn gặp nhân viên` to create a staff handoff.
7. Inspect lost order `261019QY8UDYNZ`. Its loss is backed by source scan
   `EV001358688`; the lost scenario must not execute a cancellation request.
8. Turn A3 off, then NEXT: no new proactive chats or coin grants. Existing chats
   remain available. Turn A3 on and NEXT to refresh its heartbeat; feed trust and
   any existing proactive block still apply.

## Scope and verification

This combines the operator console and simulated customer chat on one local page.
An exposed integrated server requires `LIVE_PRESENTER_KEY` and authenticates
every API request. This is presenter access, not per-customer authentication.
The Next.js `frontend/` is separate and unchanged by this integration.

```powershell
python -m pytest -q
python -m pytest -q care_truc/tests
```

The real-release integration tests require the release files above. Positive tests
label simulated staff input explicitly; their success is not a finding that source
data proves absence of force majeure. Actual RED/GREEN and browser artifacts are
stored under `.scratch/runs/integration` and `.scratch/runs/e2e-1400`.
