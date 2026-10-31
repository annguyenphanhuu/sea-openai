# Task 01: local DTOs, runtime schema and transaction/key primitives

Run alone, maximum 30 minutes from worker start. This is an implementation brief for a fresh-context worker in its assigned private worktree. No Git operations. Read workspace/repository AGENTS, `.scratch/plans/2026-10-31-execution-rules.md`, the design spec section 4 (all DTO fields/signatures) and section 5 (all companion tables), and the controller research note `.scratch/research/2026-10-31-task-01-controller.md`. User overrides in execution rules take precedence over older paths in the design. Stop and report if this task exceeds 30 minutes.

Write allowlist:

- `platform_huy/dto.py`: all frozen DTOs, protocols and PlatformError from design section 4. Imports only Python stdlib and `contracts.types`; no runtime A2 or platform imports. Keep existing Action/OrderAssessment constructors unchanged.
- `platform_huy/migrations/001_platform.sql`: companion schema from design section 5, applied only to separate runtime SQLite. Existing eight v0 tables/checks stay unchanged; no contract/source schema edits.
- `platform_huy/state.py`: canonical JSON/time, connection/bootstrap/transaction/clock functions and neutral global command-key lookup below.
- `acceptance_huy/test_task01_state.py`: only this task's new tests.
- Assigned `.scratch/runs/task-01/` command logs/receipt and `.scratch/research/` research notes. Do not write outside the task allowlist or alter existing tests.

All `contracts/` is read-only. No pytest.ini/dependency/root-configuration edits, no UI/serve_ui edits, no facade/export changes, no implementation of clock commands, A3/A2, entitlement policy or cancellation. Controller owns facade/export wiring and all Git integration.

Produce these exact primitives:

```python
canonical(value: object) -> str
utc(value: datetime) -> str
connect_state(path: Path) -> sqlite3.Connection
bootstrap(conn: sqlite3.Connection, *, run_id: str,
          identity: SourceIdentity, start_at: datetime) -> None
current_clock(conn: sqlite3.Connection) -> tuple[datetime, int]
immediate(conn: sqlite3.Connection) -> ContextManager[None]
lookup_key(conn: sqlite3.Connection, key: str) -> CommandKeyRecord | None
```

Add `CommandKeyRecord` to local dto.py with fields `namespace: str`, `key: str`, `principal_id: str | None`, `request_hash: str | None`, `reference_id: str`, `payload_json: str | None`, `result_json: str | None`. The neutral lookup inspects outbox joined to action_receipts, replay_commands, workflow_commands and eligibility_reviews under the caller's transaction. Absent returns None; a single existing namespace returns metadata; contradictory multiple namespace hits raise idempotency_conflict. For outbox, payload_json preserves its stored Action columns/evidence_ref for later authoritative recovery. A legacy row with no trusted receipt has no invented principal/hash or success. The helper does not authorize, reserve a key, deserialize every result kind, or decide blocked-benefit receipt consumption. That business question is pending Huy and belongs to Task 6.

Bootstrap must preserve the eight v0 tables and create all companion tables in one transaction, recording policy `huy-demo-v1`, immutable source/run/start identity, null business clock and null A2 checkpoint version0. An existing empty v0 state may be adopted; nonempty unattributed state, unsupported version or source/run/start mismatch must fail without writes. Apply complete SQL statements individually; do not call executescript inside an active transaction. Connections use isolation_level=None, timeout=5, foreign_keys=ON. Canonical JSON uses sorted keys, UTF-8, compact separators and allow_nan=False. UTC time requires aware input and fixed microseconds with Z suffix. BEGIN IMMEDIATE rolls back on errors; BUSY/LOCKED becomes state_busy, actual I/O failure state_unavailable; never manufacture success.

Research first: read the controller's existing Python sqlite3 and SQLite transaction references. Record the concrete choices or why no additional lookup was required. Do not print credentials or read `.env` for this task.

Required TDD and evidence:

1. Write tests with literal expected values before implementation. After import/signature scaffolding, run `python -m pytest acceptance_huy/test_task01_state.py -v` and save a genuine business assertion RED with exact command, full output, exit code and timestamp. Import failure alone is insufficient.
2. Assert bootstrap twice yields one migration row, demo_clock `(None, 0)`, replay_checkpoint `(None, 0)`, FK enabled, current_clock raises run_not_ready. Identity is SourceIdentity("a" * 64, "b" * 64, aware_start, aware_end); source identity can be a literal fixture, never release modification.
3. Test rollback with real file-backed SQLite: transaction inserts then raises, zero inserted rows afterward. Two real connections verify write contention produces state_busy and no partial changes. Failed migration/metadata adoption leaves original state intact. Test local DTO canonical/aware-time round trip, unsafe NaN and naive time rejection, unknown schema version refusal.
4. Insert isolated literal command metadata in every namespace and check lookup metadata/collision behavior. No grant/blocked policy test here. Do not mock an executor to success or add skips.
5. Run `python -m pytest acceptance_huy/test_task01_state.py acceptance_huy/test_schema_state.py acceptance_huy/test_params.py -q`. Save actual GREEN output and exit. Run fresh subprocess imports in both orders: `platform_huy.dto` then `logistics_an_nguyen.models`, and reverse; expected exit0. Do not change either imported owner module.
6. Hand off exact changed files, actual RED/GREEN evidence paths, start/end times, unresolved issues and source read/write statement. Controller obtains independent spec then quality review, integrates, runs the full pytest suite, commits and pushes existing huy after fetch/merge. Worker does no Git operations.

Literal bootstrap oracle:

```python
bootstrap(db, run_id="r", identity=identity, start_at=t)
bootstrap(db, run_id="r", identity=identity, start_at=t)
assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1
assert db.execute("SELECT current_at,version FROM demo_clock").fetchone() == (None, 0)
assert db.execute("SELECT tick_at,version FROM replay_checkpoint").fetchone() == (None, 0)
assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
```

This task is ready independently of Task 6's pending blocked-key decision. Financial keys in later tasks are exactly `xu:{order_id}` and `voucher:{order_id}`; A2/A3 never call execute_action.
