# Huy execution rules — 2026-10-31

These explicit user instructions supersede conflicting paths, ownership and scheduling in the earlier design/plan. Implementation has not started.

- Task 1 runs alone first. New DTOs and runtime migrations belong in `platform_huy/`; existing `contracts/` is read-only. Ask Huy before any contract change.
- Task 2 imports `logistics_an_nguyen.replay.ReleaseReader`; add integrity/hash validation and masking, not a replacement adapter.
- After Task 1, use at most two implementation workers, with a separate worktree per worker. Requested waves: Task 3 + 5, then 6 + 7, then 4 + 8; Task 9 last. Huy approved changing Task 3 to clock/checkpoint only and Task 4 to A3/A2/guard integration so these waves have valid dependencies.
- Workers may change only `platform_huy/`, their own task tests under `acceptance_huy/`, and assigned `.scratch` evidence. Do not change other task tests, `contracts/`, `logistics_an_nguyen/` or `care_truc/`.
- Only the controller integrates completed tasks into `huy`, runs the full pytest suite, commits and pushes. Fetch and merge remote updates before pushing. Workers never merge `main`.
- Huy separately authorized the controller to merge current completed work into `main` and push it. That authorization does not let workers modify Git integration policy.
- Each task records brief research before implementation choices, or explicitly records that no lookup was made and why a conservative approach is being used.
- Save research/spec/plan/review artifacts under `.scratch/research/`, `.scratch/specs/`, `.scratch/plans/`. Save actual RED/GREEN command output, exit codes, timestamps and task receipts under `.scratch/runs/task-NN/`.
- Expected test results are literal independent values, never computed by the function under test. Observe and save genuine RED before implementation and GREEN afterward. No executor mocked to success, no added skips.
- Financial keys are exactly `xu:{order_id}` and `voucher:{order_id}`. Each kind grants at most once per order; A2 and A3 never call `execute_action`.
- A task has a maximum of 30 minutes. On exceeding it, stop that task and report to Huy rather than continuing. At 13:00 Asia/Ho_Chi_Minh on 2026-10-31, report if Tasks 1–4 are incomplete so Huy can decide whether to cut Tasks 8–9; do not silently cut them.
- Use an independent fresh-context data auditor. Actual source data and real SQLite behavior must support verification; a fresh agent is not itself proof of correctness.
- Huy authorizes real API tests using the existing `.env` when relevant. Never print, commit or include credentials in logs. API tests supplement, not replace, deterministic platform/SQLite tests.

Current user-confirmed demo policy remains in [the decision log](../research/2026-10-31-huy-demo-decisions.md).
