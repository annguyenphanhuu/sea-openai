# Task 02 isolated implementation brief

Read this first. Execute only Task 2 below after integrated Task 1. Read workspace/repository AGENTS and execution-rules; explicit user overrides are binding. Maximum 30 minutes, record precise UTC start/deadline. No subagents or Git mutations. Source writes only platform_huy/{sources.py,validation.py,replay.py,platform.py,__init__.py,testing.py}; tests only new acceptance_huy/test_task02_*.py. Do not change Task 1 files/tests, contracts, logistics_an_nguyen or care_truc. If a shared-interface change is necessary report it to controller rather than modifying another task.

Research first using .scratch/research/2026-10-31-task-02-controller.md and the independent data audit. Data sources are the actual root checkout E:/Sea_openai/sea-openai/data/release_main, unchanged read-only; this worker's ignored data folder need not exist. Canonical production root must be configured internally by controller for this isolated verification; fixture overrides are monkeypatches in tests, not public user bypasses. Never modify source DB, sim_clock, data manifest or copy secrets. Never use truth/scoring data or audit full-data outputs as application inputs.

Existing ReleaseReader MUST be imported and used. No replacement adapter/reader. Follow source-timestamp invariant already audited, validate before assuming lexical comparisons. Actual manifest filename is manifest.sha256. Supplied DATA.md/QUICKSTART.md define release coverage; never infer coverage from earliest return. Verify source DBs and read-only rejection, preserve complete ingestion timestamp groups, validate raw visible scans before the existing reader can hide corrupt event_at, mask future cancellation/return/webhook decisions. PII should not enter safe projection.

Use Task 1 state/dto interfaces unchanged. Prototype facade exposes only implemented validation/close behavior and fail-closed service seams; do not claim A3/A2/A1 or executor implemented. Later controller wiring adds services. testing.py contains explicitly test-only literal fixtures, not production success overrides. Real source smoke checks must actually call ReleaseReader and wrapper; save exact command/case outputs and before/after hashes.

Tests: genuine business assertion RED before implementing the behavior, then GREEN. Expected values literal, no skips/no executor mocked success. Use actual SQLite files for source isolation and real release smoke. Save all output/command/exit/timestamps in .scratch/runs/task-02, research in .scratch/research/2026-10-31-task-02-sources.md. Full report .scratch/runs/task-02/task-02-report.md includes frozen helper/facade signatures for subsequent pairs. Worker no Git; controller reviews/integrates/full pytest/commits/fetches/merges/pushes.

The plan text below is subordinate to this scope and latest decisions. Financial blocked-key policy remains pending and is not part of Task 2.
### Task 2: Read-only source identity, visible validation và replay

**Files:** Create `platform_huy/sources.py`, `platform_huy/validation.py`, `platform_huy/replay.py`, `platform_huy/platform.py`, `platform_huy/__init__.py`, `platform_huy/testing.py`, `acceptance_huy/test_task02_replay.py`. Sequential Task 2 freezes common fixture and facade hooks before waves.

**Interfaces:** Import and reuse existing `logistics_an_nguyen.replay.ReleaseReader` and ReplaySnapshot unchanged. Sources owns `.reader = ReleaseReader(core_path)` and `.core = reader.connection`; only supplemental ops connection is opened locally. `Sources(core_path: Path, ops_path: Path)` provides `.core/.ops: sqlite3.Connection`, `validate() -> SourceIdentity`, `close() -> None`; `project(sources: Sources, *, tick_at: datetime, previous_watermark: datetime | None) -> Projection`. Frozen Projection fields: `snapshot: ReplaySnapshot`, `raw_visible: dict[str,tuple[dict,...]]`, `scan_delta_ids: tuple[str,...]`, `scan_watermark: datetime | None`, `quarantined_order_ids: tuple[str,...]`, `corrupt_feeds: tuple[str,...]`, `incidents: tuple[dict,...]`. A2 imports only in Huy modules. raw_visible allowlists no PII; includes needed orders/scans/attempts/reports/returns/ledger/external_events/ops facts.

- [ ] **Step 1 — fixture DDL and RED cursor/masks/readonly.** `source_files` fixture produces root/core_path/ops_path/writable core+ops, `freeze() -> tuple[Path,Path]`; seed test-only minimal columns/PKs matching actual projection. Additional external_events/ops columns for evidence resolver must match actual schema inspected through PRAGMA, not invented proof fields.

```python
CORE_SQL = """
CREATE TABLE orders(order_id TEXT PRIMARY KEY,customer_id TEXT,seller_id TEXT,created_at TEXT,guaranteed_date TEXT,carrier_id TEXT,service_level TEXT,items_value_vnd INTEGER,cancelled_at TEXT,cancel_actor TEXT,cancel_reason TEXT);
CREATE TABLE scan_events(event_id TEXT PRIMARY KEY,order_id TEXT,status TEXT,location_type TEXT,location_id TEXT,event_at TEXT,ingested_at TEXT,carrier_event_id TEXT);
CREATE TABLE delivery_attempts(attempt_id TEXT PRIMARY KEY,order_id TEXT,attempt_no INTEGER,attempt_at TEXT,outcome TEXT,reason_code TEXT,call_attempts INTEGER);
CREATE TABLE linehaul_reports(report_id TEXT PRIMARY KEY,trip_id TEXT,reported_at TEXT,reported_by TEXT,reason_code TEXT,driver_note TEXT);
CREATE TABLE returns(return_id TEXT PRIMARY KEY,order_id TEXT,requested_at TEXT,reason TEXT,status TEXT,decided_at TEXT,refund_vnd INTEGER);
CREATE TABLE compensation_ledger(entry_id TEXT PRIMARY KEY,order_id TEXT,kind TEXT,amount_vnd INTEGER,actor TEXT,reason_text TEXT,created_at TEXT,idempotency_key TEXT,source_ref TEXT);
CREATE TABLE external_events(event_id TEXT PRIMARY KEY,ts TEXT,kind TEXT,province_code TEXT,title TEXT,detail TEXT);
"""
T = datetime.fromisoformat("2026-10-31T00:00:00+07:00")
def seed_base(core: sqlite3.Connection, items_value: int | None) -> None:
    core.executemany("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?)", [
        ("o", "c", "s", "2026-10-28T00:00:00+07:00", "2026-10-29", "SAO", "standard", items_value, None, None, None),
        ("fresh", "f", "s", T.isoformat(), "2026-11-02", "SAO", "standard", 100000, None, None, None)])
    core.execute("INSERT INTO scan_events VALUES(?,?,?,?,?,?,?,?)", (
        "e", "o", "lost", "station", "st", T.isoformat(), T.isoformat(), None))
    core.execute("INSERT INTO delivery_attempts VALUES(?,?,?,?,?,?,?)", (
        "a", "fresh", 1, T.isoformat(), "delivered", None, 1))
```

In platform_huy/testing.py import datetime/sqlite3; OPS fixture exact projected DDL metrics composite(ts,service_id,metric)/value; logs(log_id,ts,service_id), alerts(alert_id,ts,service_id), deploy_events(deploy_id,ts,service_id), webhook_inbox(msg_id,received_at,processed_at), plus actual structured fields when resolver tests use them. freeze writes hashes for DBs and fixture documentation carrying coverage bounds; no reading metadata.yml/truth queries. Source test inserts 12 event IDs e00–e11 same ingested_at=T, event_at=T−1h: assert full delta tuple once, watermark=T, retry previous_watermark=T empty, full snapshot still12; future ingest T+1us invisible. Raw corruption separate fixture before freeze.
- [ ] **Step 2 — RED:** `python -m pytest acceptance_huy/test_task02_replay.py -v`; expected visibility/mask/complete-group assertions FAIL, not fixture path rejection.
- [ ] **Step 3 — implement immutable validation and projection.** Production RELEASE_ROOT canonical data/release_main; require correct basenames/paths, reject symlink escape/source=state. `mode=ro`, query_only ON, PK/columns/quick_check/manifest SHA once per run. Verify documented coverage `2026-10-18T00:00:00+07:00` through `2026-11-08T23:59:59.999999+07:00` against release docs/manifest, do not use observed MIN(return). Parse instants before cutoff unless offset/precision invariant verified; preserve microseconds cutoff.

```python
# Supplemental ops only; core always uses existing ReleaseReader.
def open_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path.resolve(strict=True).as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn

def mask_return(row: dict, tick_at: datetime) -> dict:
    result = dict(row)
    if row["decided_at"] is None or datetime.fromisoformat(row["decided_at"]) > tick_at:
        result.update(status="requested", decided_at=None, refund_vnd=None)
    return result
```

Get base A2 snapshot from `reader.snapshot(tick_at)`; surrounding raw-visible validation catches corruption the reader filters, and allowlisted supplemental queries add missing fields/masks. Do not duplicate the four base queries or change A2 reader/adapter. Validate actual uniform timestamp precision before relying on its second-precision cutoff; unsupported precision must fail clearly, not silently hide rows.

Validate availability before semantic fields: malformed availability source_invalid because cutoff unknowable; future rows' semantic errors do not corrupt past. Raw scan ingested<=T validate event<=ingested, aware timestamps, enum/identity/join; visible error marks entire feed corrupt plus incident, never hidden by A2 event<=T query. Invalid guarantee quarantine+orders corrupt, no ETA fallback. Full snapshot joins only visible valid orders, scans sort event_at/event_id; delta uses previous_watermark<ingested<=T ordered ingestion/event_id and completes whole timestamp group before checkpoint. Mask cancellation trio, return decision/refund, webhook processed. Ledger read direct by order created_at<=T, not inner join dropping outside-slice history. planned trips excluded. Ops incident cannot independently invent business deny threshold or restore freshness from payment/voucher service. Projection dict copied per attempt, not deeply immutable claim.
- [ ] **Step 4 — GREEN:** `python -m pytest acceptance_huy/test_task02_replay.py -q`; readonly UPDATE/CREATE INDEX errors+hash unchanged, 12-row group, future event visibility/semantic isolation, malformed availability failclosed, all masks literal nulls, future order join excluded. Constructor stores validated identity through Task1 bootstrap, rejects run/source mismatch.
- [ ] **Step 5 — GATE:** clean review, controller commit `feat: validate immutable source projections and ingestion cursor`, push huy.

Frozen fixture signature: `platform_factory(*, items_value: int | None = 239999, request_rule: ExplicitRequestRule | None = None, before_freeze: Callable[[sqlite3.Connection, sqlite3.Connection], None] | None = None) -> tuple[Platform, dict]`. Returns platform and constructor kwargs, fixture source seed before readonly freeze, no attempt initialized by default. `actor(source: ActionSource | None = "a1", *, customer_id: str | None = "c", seller_id: str | None = None, capabilities: frozenset[str] | None = None) -> ServerContext` derives fixture contexts; operator is source None with explicit human capabilities. `seed_component_ready` is the only named prerequisite fixture seeder, never runtime code. New task-specific helpers such as benefit_action belong to that task test file, not testing.py. Task 5's build_eligible_case/eligible is importable from its owned test file.

Task 2 freezes `platform_huy/testing.py` with T/source_files/platform_factory/seed_base/actor/operator/FixtureRequestRule and `seed_component_ready(p) -> None`. Tests explicitly import fixtures. The latter inserts documented literal coherent prerequisite rows in isolated real SQLite only (clock, attempt, assessment, health/checkpoint); it never mocks executor success, writes release data, or proves A3/A2 pipeline success. Tasks 5-7 component tests may use it before Task 4. Task 4 runs separate public-API integration tests without seeded success. Later tasks own any new helper in their own test file; never change shared fixtures in waves. Facade provides fail-closed typed service registration hooks; controller binds completed services after handoff.


