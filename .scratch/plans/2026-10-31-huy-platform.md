# Huy Demo Platform Implementation Plan

> **Execution adaptation 2026-10-31:** Follow execution-rules and execution-preflight. Task 1 ready alone; Huy confirmed only successful grants reserve financial keys. This document records plans, not executed tests.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hoàn tất nền Python demo của Huy: NEXT thủ công, A3/A2, chat provenance, xác minh nhân viên, hai quyền lợi nội bộ, hủy hai lượt và thống kê trả hàng của shop.

**Architecture:** Một SQLite authority/run, nguồn release read-only. Manual clock và attempt commit trước compute; A3 commit riêng; A2 snapshot/progress/checkpoint publish nguyên tử. Executor recheck current clock, review head, source facts và ledger đúng kind trong cùng transaction, rồi ghi local entitlement + receipt.

**Tech Stack:** Python 3.11+, standard library SQLite/dataclasses/datetime/hashlib/json/argparse, pytest hiện có; không dependency mới.

**Spec:** [2026-10-31-huy-platform-design.md](../specs/2026-10-31-huy-platform-design.md); [demo re-review: Approved](../specs/2026-10-31-huy-demo-spec-review.md). [Decision log](../research/2026-10-31-huy-demo-decisions.md) và [release cases](../research/2026-10-31-huy-demo-cases.md) là căn cứ policy và dữ liệu cho plan này.

**Status:** Adapted for controller review; Financial retry policy confirmed. Đây là plan, chưa chạy implementation/tests/commands bên dưới.

## Global Constraints

- Runtime nằm trong `runs/<run_id>/state.sqlite`.
- Tất cả datetime aware; state/wire UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`; guaranteed_date giữ ngày VN.
- Coins 5% giá trị items, floor1.000, min10.000/max1.000.000, None/0→10.000; voucher cố định10.000 VND.
- Hai khoản cùng điều kiện: trễ >=2 ngày lịch VN, khách tự yêu cầu TEXT trong chat A1 mở, không lỗi khách/không bất khả kháng.
- Cho phép nhận cả hai qua **hai authorized Action riêng**, mỗi loại once/order; một call/message không tự kích hoạt hai khoản, khoản này không tiêu thụ quyền khoản kia.
- Scope chỉ issuance nội bộ: không redemption/expiry, không tự tạo TTL, minimum spend, mã dùng tại Shopee hoặc lời hứa provider.
- `simulated_now = demo_clock.current_at`, durable độc lập A2 checkpoint.
- Chat server tự gán created_at=now và lưu received_at wall UTC audit, phản hồi ngay không đợi tick.
- Đúng ba required feeds A2 hiện có: orders, scan_events, delivery_attempts; health global theo feed.
- Quá 30 phút nguồn mới stale, không phải >=30. Thiếu/quá 60 phút heartbeat hoặc feed unusable chặn proactive.
- Busy timeout5s trả state_busy, không success giả hoặc vô hạn retry.
- Giữ nguyên tám bảng v0 và CHECK/FK/UNIQUE hiện có; không thêm trigger khiến fixture INSERT v0 của acceptance_huy hỏng.
- Shared DTOs chỉ import stdlib và contracts.types, không runtime-import logistics_an_nguyen hoặc platform_huy.
- Latest revision luôn là head kể cả unknown/present/fingerprint invalid; không tìm “latest verified” phía sau.
- Refund/shipping_fee_refund vẫn policy_not_configured.
- `review_required=None`, `threshold_policy=None`; không fraud label, ratio, threshold hoặc automatic review/denial.
- Không source writes/sim_clock/index/truth/heldout/world generation; không provider/HTTP/voice framework, rebuild A2 hoặc tự viết A1.

## Execution, ownership and receipts

Use the already selected Superpowers subagent-driven-development workflow: fresh-context bounded implementer; independent spec then quality review; fixes/review before integration. At most TWO coding workers, each in a separate worktree. Workers perform NO Git operations. Controller alone integrates, modifies shared facade/exports, commits and pushes.

Order: **1 alone -> 2 sequentially -> 3+5 -> 6+7 -> 4+8 -> 9**. Task 3 is clock/checkpoint only; Task 4 owns actual A3->A2 orchestration and guard. Each task has a 30-minute cap: stop and report if exceeded. At 13:00 Asia/Ho_Chi_Minh on 2026-10-31, if Tasks 1-4 incomplete, notify Huy to decide whether to cut 8-9; never cut silently.

Before work and every push, controller fetches upstream, merges upstream/huy and upstream/main into existing huy. After EACH completed task, controller integrates exact allowlist, runs full `python -m pytest -q -rA`, obtains review, commits, fetches/merges again, reruns verification if merged code changed, pushes huy. Controller is now explicitly authorized to merge verified completed work into main and push main. No worker Git, hooks, branch recreation, rename or force push.

Implementation source only platform_huy, excluding Truc UI/serve_ui. New tests only own `acceptance_huy/test_taskNN_*.py`. Existing tests/modules, contracts, pytest.ini, root configuration/dependencies are read-only; ask Huy before any contracts edit. Controller-only platform.py/__init__.py wiring occurs after handoff; parallel workers never overlap them or common fixtures.

Every task first records research or why no lookup was needed. Artifacts stay in .scratch/research, .scratch/specs and .scratch/plans; actual RED/GREEN output, commands, exit codes, timestamps, task receipts and hashes go in .scratch/runs/task-NN. Literal oracles precede code. Import failure alone is insufficient: observe actual business-assertion RED before GREEN. No added skips, owner-test weakening, or executor mocked to success. Independent fresh-context data auditor must inspect actual release rows and real SQLite behavior. Relevant authorized API tests may use existing .env without printing/logging credentials; they supplement deterministic verification.

Fixed financial keys are exactly `xu:{order_id}` and `voucher:{order_id}`. A2/A3 never call execute_action. Huy confirmed success-only key reservation. Task 6 records denied financial attempts as structured incidents without financial outbox/receipt/ledger inserts, then permits full re-evaluation under the same key before success. Task 1 neutral lookup remains unchanged. Approved eligibility, amounts, per-kind history and success receipt replay remain unchanged.

## File map and test fixtures

All new DTO/protocol/error definitions: platform_huy/dto.py, imports only stdlib and contracts.types. Runtime schema: platform_huy/migrations/001_platform.sql, existing contracts entirely read-only. state.py owns transaction/key primitives; tick.py owns clock/checkpoint; orchestration.py owns A3/A2; sources/validation/replay wrap existing ReleaseReader; guard/views current trust and read view; provenance/reviews/evidence_refs audited authority; execution/cancellation independent services; return_history scoped counts; demo/recovery CLI and exact original Action retry. Controller owns platform.py/__init__.py wiring only. testing.py is fixed in Task 2. Tests are each task's acceptance_huy/test_taskNN_*.py, with no other test modifications.

Fixtures tạo source **test** tối thiểu trước freeze trong `runs/test-huy-<uuid>/release_main/`, state cùng unique run root; không dùng release DB để seed. Source fixture freeze đóng writable connections, hash manifest; monkeypatch nội bộ sources.RELEASE_ROOT sang fixture root, không public bypass. Actual source default `data/release_main`. QuestionStore persistent state bắt buộc dưới repository runs/; ordinary tmp_path chỉ cho test không tạo QuestionStore. Cleanup kiểm resolved target nằm trong đúng unique root dưới runs rồi mới xóa; không xóa runs tổng.

### Task 1: Local DTOs, companion migration và transaction primitives

**Files:** Create `platform_huy/dto.py`, `platform_huy/migrations/001_platform.sql`, `platform_huy/state.py`, `acceptance_huy/test_task01_state.py`. No contracts, exports, pytest.ini or root edits. See standalone task-01-brief.md.

**Interfaces:** Consumes v0 SQL/Action/OrderAssessment; produces mọi frozen DTO/protocol/PlatformError spec4, gồm TickAttempt/CurrentGuard/CommittedView/EligibilityReviewDecision và ExecutionResult mới có kind/coin/voucher fields. Helpers: `canonical(value: object) -> str`, `utc(value: datetime) -> str`, `connect_state(path: Path) -> sqlite3.Connection`, `bootstrap(conn: sqlite3.Connection, *, run_id: str, identity: SourceIdentity, start_at: datetime) -> None`, `current_clock(conn: sqlite3.Connection) -> tuple[datetime,int]`, `immediate(conn: sqlite3.Connection) -> ContextManager[None]`.

- [ ] **Step 1 — RED migration/clock/import tests.**

```python
def test_bootstrap_does_not_initialize_business_clock(tmp_path):
    import pytest
    from datetime import datetime, timezone
    from platform_huy.dto import PlatformError, SourceIdentity
    from platform_huy.state import bootstrap, connect_state, current_clock
    db = connect_state(tmp_path / "state.sqlite")
    t = datetime(2026, 10, 30, 17, tzinfo=timezone.utc)
    identity = SourceIdentity("a" * 64, "b" * 64, t, t)
    bootstrap(db, run_id="r", identity=identity, start_at=t)
    bootstrap(db, run_id="r", identity=identity, start_at=t)
    assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1
    assert db.execute("SELECT current_at,version FROM demo_clock").fetchone() == (None, 0)
    assert db.execute("SELECT tick_at,version FROM replay_checkpoint").fetchone() == (None, 0)
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(PlatformError) as error:
        current_clock(db)
    assert error.value.code == "run_not_ready"
    db.close()
```

- [ ] **Step 2 — run RED:** `python -m pytest acceptance_huy/test_task01_state.py -v`; expected clock/migration assertion FAIL after imports/stubs exist. Add actual subprocess import-order tests contracts→A2.models and reverse, expected exit0 after implementation.
- [ ] **Step 3 — implement DTOs + full migration spec5**, including demo_clock/tick_attempts/replay_commands/voucher_ledger/eligibility_reviews, all other companion tables, JSON/enum/FK/version checks. policy_version `huy-demo-v1`; customer_messages includes business created_at + received_at audit. Preserve separate UNIQUE(order_id) per ledger. Bootstrap v0+001+metadata+null clock/checkpoint in one transaction, adopt only empty eight v0 tables; unknown version/nonempty unattributed state/mismatch run/source/start source_invalid with no writes. Execute SQL complete statements individually, not executescript in active transaction.

```python
def current_clock(conn: sqlite3.Connection) -> tuple[datetime, int]:
    row = conn.execute("SELECT current_at,version FROM demo_clock WHERE singleton=1").fetchone()
    if row is None or row[0] is None:
        raise PlatformError("run_not_ready")
    return datetime.fromisoformat(row[0].replace("Z", "+00:00")), row[1]

@contextmanager
def immediate(conn: sqlite3.Connection):
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield
        conn.commit()
    except sqlite3.OperationalError as error:
        conn.rollback()
        if getattr(error, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            raise PlatformError("state_busy") from error
        raise PlatformError("state_unavailable") from error
    except BaseException:
        conn.rollback()
        raise
```

`connect_state`: isolation_level=None, timeout=5, foreign_keys ON. `canonical`: sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",",":"). `utc` rejects naive validation_error, UTC microseconds Z. SQL integrity/validation errors retain stable public PlatformError codes; do not translate a programming bug into success. State I/O failure live gate state_unavailable denial; never claim audit persisted when write failed.
- [ ] **Step 4 — GREEN:** `python -m pytest acceptance_huy/test_task01_state.py acceptance_huy/test_schema_state.py acceptance_huy/test_params.py -q`; exit0, no owner-test changes. Import two orders in fresh subprocesses exit0; JSON/datetime round-trip and metadata/checkpoint atomic rollback asserted.
- [ ] **Step 5 — GATE:** clean review, controller commit `feat: add demo platform contracts and transactional runtime schema`, push huy.

Task 1 additionally owns frozen `CommandKeyRecord(namespace: str, key: str, principal_id: str | None, request_hash: str | None, reference_id: str, payload_json: str | None, result_json: str | None)` in dto.py and `lookup_key(conn: sqlite3.Connection, key: str) -> CommandKeyRecord | None` in state.py. Inspect outbox joined action_receipts, workflow_commands, replay_commands and eligibility_reviews under caller transaction; absent None, one neutral metadata result, contradictory namespaces idempotency_conflict. Preserve stored Action columns/evidence for later recovery; legacy records have no invented trusted hash/principal/success. Do not authorize, reserve key, decide blocked-key policy or decode every result kind. Existing services compare metadata themselves. Task 1 standalone brief is authoritative on path/interface adaptation.

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

### Task 3: Manual clock, durable attempts and checkpoint primitives ONLY

**Files:** Create `platform_huy/tick.py`, `acceptance_huy/test_task03_clock.py`; assigned .scratch/runs/task-03. No orchestration, guard, facade, fixture or Task 5 edits.

**Interfaces:** Consume state/dto and Task 1 lookup_key. Produce `ClockService(platform).initialize(*, idempotency_key: str, context: ServerContext) -> TickAttempt`, `.advance(*, expected_clock_version: int, idempotency_key: str, context: ServerContext) -> TickAttempt`, `.retry(*, expected_clock_version: int, idempotency_key: str, context: ServerContext) -> TickAttempt`. These schedule current attempt ONLY. Produce `publish_checkpoint(conn, *, attempt_id: str, retry_count: int, clock_version: int, expected_checkpoint_version: int, tick_at: datetime, scan_watermark: datetime | None, progress_json: str, result_json: str) -> None`, called within caller's existing immediate transaction. Final public Platform commands retain spec signatures and call Task 4 coordinator after scheduling when integrated.

- [ ] **Step 1 - literal RED cases.** Bootstrap current_at None/version0; initialize schedules pending at `2026-10-30T17:00:00.000000Z`/version1; repeat init key same attempt. Pending blocks NEXT. Explicit isolated failed-attempt fixture enables NEXT `2026-10-30T17:30:00.000000Z`/version2. No integration success claim.

```python
def test_schedule_never_publishes_a3_or_a2(clock_case):
    service, conn, staff = clock_case
    first = service.initialize(idempotency_key="init", context=staff)
    assert (first.status, first.a3_status) == ("pending", "pending")
    assert conn.execute("SELECT current_at,version FROM demo_clock").fetchone() == ("2026-10-30T17:00:00.000000Z", 1)
    assert conn.execute("SELECT tick_at,version FROM replay_checkpoint").fetchone() == (None, 0)
    assert conn.execute("SELECT COUNT(*) FROM guard_heartbeat").fetchone()[0] == 0
```

- [ ] **Step 2 - actual RED:** `python -m pytest acceptance_huy/test_task03_clock.py -v`, business assertion failure after signature scaffolding, save actual output/exit/timestamp.
- [ ] **Step 3 - minimal implementation:** human replay:advance, neutral key lookup first, hash operation/principal/expected_version. Init saved start_at; NEXT exactly +30min, no target/wall time. Atomic clock+attempt+command receipt before compute. Same key same attempt status, mismatched semantics/principal conflict. Pending/running blocks new NEXT; failed allows retry or NEXT. Retry same now increments retry_count; succeeded retry no recompute. Checkpoint publication CAS verifies clock/version/attempt/retry_count/checkpoint version and rollback leaves old state. No A3/A2 imports, guard calculation or execute_action calls.
- [ ] **Step 4 - GREEN:** `python -m pytest acceptance_huy/test_task03_clock.py -q`. Real two-connection version race advances once; response-loss/reopen same key never advances; interrupted pending remains degraded; failed command never rewinds clock; stale publication and authorizer-denied checkpoint UPDATE rollback. Check shared namespace collisions. Literal expected values only.
- [ ] **Step 5 - GATE:** independent spec then quality review; controller full pytest, commit `feat: add durable clock and checkpoint primitives`, fetch/merge, verify and push huy. Pending component state is not a completed tick.

### Task 4: A3 -> A2 integration plus Current guard, sticky control và consistent committed view

**Files:** Create `platform_huy/orchestration.py`, `platform_huy/guard.py`, `platform_huy/views.py`, `acceptance_huy/test_task04_pipeline.py`, `acceptance_huy/test_task04_guard.py`, `acceptance_huy/test_task04_views.py`. Controller wires facade after handoff; no Task 3 tick.py or Task 8 edits.

**Interfaces:** Consume ClockService/publish_checkpoint from Task 3. Produce `TickCoordinator(platform).run_current() -> StoredTick`, `health_for(projection: Projection, *, tick_at: datetime) -> tuple[FeedHealthRecord,...]` and feed_status. All actual A3/A2 work belongs here. Platform.can_proactively_contact/set_proactive_control/get_committed_view exact spec4. `evaluate_gate(*, now: datetime, heartbeat_at: datetime | None, health: tuple[FeedHealthRecord,...], required_feeds: tuple[str,...], control_allowed: bool, attempt_succeeded: bool, assessment_current: bool) -> GateDecision`; `read_view(platform: Platform, *, order_id: str | None, context: ServerContext) -> CommittedView`. View clock/attempt/A2/guard/control/reviewhead/ownership checks share **one read transaction**.

- [ ] **Step 1 — RED literal freshness and new A3/old A2 separation.**

```python
@pytest.mark.parametrize("age,status", [(1799, "trusted"), (1800, "trusted"), (1800.000001, "stale")])
def test_source_age_boundary(age, status):
    from datetime import timedelta
    from platform_huy.guard import feed_status
    from platform_huy.testing import T
    assert feed_status(now=T, source_at=T-timedelta(seconds=age), corrupt=False) == status

def test_current_a3_is_exposed_before_any_a2_publication(platform_factory, monkeypatch):
    import platform_huy.orchestration as tick
    from platform_huy.testing import T, operator
    p, kwargs = platform_factory()
    def fail(*args, **kwargs):
        raise RuntimeError("A2 failure")
    monkeypatch.setattr(tick, "evaluate_tick", fail)
    p.initialize_tick(idempotency_key="init", context=operator())
    view = p.get_committed_view(context=operator())
    assert view.current_at == T and view.latest_tick is None
    assert view.assessment_current is False
    assert view.current_guard.snapshot_tick_at == T
    assert view.current_guard.a3_status == "completed"
    assert len(view.current_guard.feed_health) == 3
    assert view.current_guard.effective_proactive_gate.allowed is False
```

Moved real-pipeline rollback oracle:

```python
def test_a3_survives_first_a2_failure_and_clock_is_durable(platform_factory, monkeypatch):
    import platform_huy.orchestration as tick
    from platform_huy.platform import Platform
    from platform_huy.testing import T, operator
    p, kwargs = platform_factory()
    def fail_a2(*args, **kwargs):
        raise RuntimeError("injected A2 failure")
    monkeypatch.setattr(tick, "evaluate_tick", fail_a2)
    attempt = p.initialize_tick(idempotency_key="init", context=operator())
    assert (attempt.status, attempt.a3_status) == ("failed", "completed")
    assert p._connection.execute("SELECT COUNT(*) FROM guard_heartbeat").fetchone()[0] == 1
    assert p._connection.execute("SELECT COUNT(*) FROM feed_health").fetchone()[0] == 3
    assert p._connection.execute("SELECT tick_at,version FROM replay_checkpoint").fetchone() == (None, 0)
    assert p._connection.execute("SELECT COUNT(*) FROM a2_progress").fetchone()[0] == 0
    assert p._connection.execute("SELECT value_json FROM controls").fetchone()[0] == "false"
    p.close()
    resumed = Platform(**kwargs)
    assert resumed.initialize_tick(idempotency_key="init", context=operator()).attempt_id == attempt.attempt_id
    assert resumed._connection.execute("SELECT current_at,version FROM demo_clock").fetchone() == ("2026-10-30T17:00:00.000000Z", 1)
    resumed.close()
```

- [ ] **Step 2 — RED:** `python -m pytest acceptance_huy/test_task04_pipeline.py acceptance_huy/test_task04_guard.py acceptance_huy/test_task04_views.py -v`; expected current guard vs historical state assertions FAIL.
- [ ] **Step 3 — implement current authorization, never relabel StoredTick.**

```python
def feed_status(*, now, source_at, corrupt):
    if corrupt:
        return "corrupt"
    if source_at is None:
        return "missing"
    return "stale" if now-source_at > timedelta(minutes=30) else "trusted"

# health_for uses these source columns, not processing/ingestion recency.
SOURCE_FIELDS = {"orders": "created_at", "scan_events": "event_at", "delivery_attempts": "attempt_at"}
```

A3 compute validates projection, global health MAX orders.created_at/scans.event_at/attempts.attempt_at; scan last_ingested separate. Corrupt>missing>stale>trusted; >30 only. Commit actual heartbeat/health/incidents/tighten + a3_status completed **before** A2. Completed A3 same tick/identity reused on A2 retry. A3 unsafe/timeout/error rollback its work, separate failure transaction persists attempt failed/errors/incident/stickyfalse, no success heartbeat. State unwritable state_unavailable/live deny, never fake persisted incident. No invented timeout threshold; monotonic for configured runtime timeout, not simulated time.

A2 attempt starts fresh ProgressTracker from last committed a2_progress.records_json; ReleaseAdapter(full cumulative snapshot).orders(), tracker.apply exact A2 FeedHealth mapped1:1, evaluate_tick. Atomic A2 transaction writes assessments/quarantine/questions via QuestionStore(connection), progress JSON, watermark, tick_results/hash/required_feeds_by_order, replay_checkpoint.version+1 and attempt succeeded. Exception rollback A2 only, discard tracker, persist failure/deny separately; unexpected exception fails batch, no fake per-order result. After gap from failed Next, A2 tracker resets per existing logic, do not synthesize missing intervals. run_tick tick_at!=now tick_sequence_invalid; old StoredTick reads via view only, no time advance. No A1/network in transaction; handoff pending_integration with stable run/tick/order key.


Gate preinit false run_not_ready; state unavailable false state_unavailable; current pending/failed false tick_unavailable even with old healthy heartbeat at frozen time. Require current committed assessment and server required_feeds_by_order, latest actual A3<=now, heartbeat age<=60min, each A2 FeedHealth.usable_at(now), sticky true. Missing heartbeat false, future heartbeat unusable. No caller facts/dependency truncation/time. Tightening sourceNone controls:tighten true→false only; A3 false→true control_relaxation_denied. Human controls:release only current succeeded, no newer failure, same current gate excluding stickyfalse; at<=now audit, backdating cannot choose oldhealth. Release + incident audit one transaction. Recovery health never auto releases stickyfalse. Inbound/cancel/handoff not blanket banned.

View state:read gives CurrentGuard current attempt only: A3completed actual current heartbeat/feed rows even A2failed; A3pending/failed/missing snapshot_tick_at/heartbeat null, feeds empty, truthful status/gate reasons. StoredTick.feed_health frozen publication health. global gate only global prerequisites; order gate adds own current assessment/dependencies. Customers/sellers ownorder only, current_guard None without state:read; absent/foreign order not_found; allorders needs state:read. Begin deferred read transaction before first SELECT, deserialize after snapshot captured, no mixed clock versions across Next. Gate short read transaction serializes reads with controls/clock; no lock held over transport.
- [ ] **Step 4 — GREEN:** `python -m pytest acceptance_huy/test_task04_pipeline.py acceptance_huy/test_task04_guard.py acceptance_huy/test_task04_views.py -q`; heartbeat59:59/60:00 pass age-only,60:00.000001 false; source event10/ingest11/T11 stale despite fresh paymentmetric; corrupt row beats MAX. A3T+30/A2fail view actualguardT+30 + historical StoredTickT, firstA2fail latestnull. Concurrent Next/view internally same clockversion; ownorder hides guard/otherorder. Backdated control/open cannot authorize oldhealthy. Pending restart denied; unavailable state test no fabricated incident.
- [ ] **Step 5 — GATE:** clean review, controller commit `feat: expose consistent current guard and authorized demo views`, push huy.

Run actual public Platform initialization/NEXT, real ReleaseReader/ReleaseAdapter/ProgressTracker/evaluate_tick, actual shared executor and real file-backed SQLite for integration regressions from Tasks 3,5,6,7. No seeded succeeded attempt in these tests. Assert A3 own commit survives A2 failure, A2 batch/checkpoint rollback, gap/restart and no double progress, proactive guard and both benefit gates. Only this gate establishes actual staged pipeline integration.

### Task 5: Immediate chat provenance và ordered human review authority

**Files:** Create `platform_huy/provenance.py`, `platform_huy/reviews.py`, `platform_huy/evidence_refs.py`, `acceptance_huy/test_task05_provenance.py`, `acceptance_huy/test_task05_reviews.py`. Controller wires facade; no shared fixture edits.

**Interfaces:** Exact Platform record_contact_opened/record_customer_message/prepare_execution_evidence/record_eligibility_review/withdraw_eligibility_review/get_eligibility_review_revision từ spec4. Internal `resolve_ref(platform: Platform, ref: str, *, order_id: str, as_of: datetime, note: str) -> dict`; `material_fingerprints(platform: Platform, order_id: str, *, as_of: datetime, decision: EligibilityReviewDecision | None) -> dict[str,str]` keys common/coins_history/voucher_history; `review_head(conn: sqlite3.Connection, order_id: str) -> dict | None`; `build_current_evidence(platform: Platform, order_id: str, *, contact_id: str | None, message_id: str | None, context: ServerContext) -> dict`. `actor(source: ActionSource | None="a1", *, customer_id: str | None="c", seller_id: str | None=None, capabilities: frozenset[str] | None=None) -> ServerContext` testhelper; default own c with contacts:write/actions:coins/actions:read/cancel:request/confirm/read, source rule gets actions:voucher, source app no entitlement cap. operator separate staff context.

- [ ] **Step 1 — RED signal timestamp/authority and same-clock revision tests.** FixtureRequestRule deterministic version fixture-v1 recognizes exact body `Tôi yêu cầu bồi thường do giao trễ`; fixture adapter **test only**, no production keyword matcher. Tests import pytest/datetime normally at file header.

```python
def test_message_uses_simulation_now_not_wall_receipt(platform_factory):
    from datetime import timedelta
    from platform_huy.testing import T, actor, operator, FixtureRequestRule, seed_component_ready
    p, kwargs = platform_factory(request_rule=FixtureRequestRule())
    seed_component_ready(p)  # labeled real SQLite prerequisite fixture; integration in Task 4
    p.record_contact_opened(contact_id="chat", order_id="o", channel="chat",
        proactive=True, opened_at=T, context=actor())
    p.record_customer_message(message_id="m", contact_id="chat",
        body="Tôi yêu cầu bồi thường do giao trễ", origin="text",
        received_at=T+timedelta(minutes=17), context=actor())
    assert p._connection.execute("SELECT created_at,received_at,request_code FROM customer_messages").fetchone() == (
        "2026-10-30T17:00:00.000000Z", "2026-10-30T17:17:00.000000Z", "late_compensation")
    assert p._connection.execute("SELECT version FROM demo_clock").fetchone()[0] == 1
```

Add review test record r1 expected0 then full replacement r2 expected1 at same now; getter2, head r2 even responsibility/FM unknown, r1 audit unchanged. Withdraw expected2 appends r3 withdrawn/fourfields unknown; duplicate key returns r3 ID without revision4. Foreign/nonhuman/emptyproof/duplicate fieldkeys rejected, zero review rows.
- [ ] **Step 2 — RED:** `python -m pytest acceptance_huy/test_task05_provenance.py acceptance_huy/test_task05_reviews.py -v`; expected server-clock/minted-signal/reviewhead assertions FAIL before implementation.
- [ ] **Step 3 — implement contact/message/evidence and human audit.** Every mutation immediate transaction reads current_clock/version, no preinit writes. Contact needs contacts:write+ownership, proactive a1+currentgate, initiated_by server A1; inbound app→customer, stays available during failed attempt. IDs immutable samefacts noop/differentfacts idempotency_conflict. Message has **received_at**, no caller created_at: aware wall audit may exceed business now; assign created_at=now, require valid contact opened_at<=now<=closed_at if closed; trusted origin text/voice, original body immutable. Rule only text+A1-opened chat, true mints code/version; absent/false null; exception rollback source_invalid. No TTL, voice never signal, no client request_code field.

```python
def review_head(conn: sqlite3.Connection, order_id: str) -> dict | None:
    cursor = conn.execute("SELECT * FROM eligibility_reviews WHERE order_id=? ORDER BY revision DESC LIMIT 1", (order_id,))
    row = cursor.fetchone()
    return dict(zip((c[0] for c in cursor.description), row)) if row else None

# Under BEGIN IMMEDIATE, after shared-key replay/collision checks.
head = review_head(connection, order_id)
revision = head["revision"] if head else 0
if revision != expected_revision:
    raise PlatformError("version_conflict")
new_revision = revision + 1
# INSERT immutable full four-field decision, revision=new_revision.
```

Human eligibility:review+sourceNone, nonempty reason, evidence_as_of==now. Four fields exact spec9, unique allowed mapkeys; nonunknown fields require visible structured refs+method/scope note. Record fullreplacement no merge/patch; withdrawal append unknownfields statewithdrawn, audit/sourceidentity/fingerprints/refvalues/hash, not DELETE. Stable review key namespace checks across outbox/workflow/replay/reviews, binds operation/principal/order/decision/expectedrevision/reason/evidenceasof; retry returns original ID before headversion check. Latest integerrevision wins even sameclock/invalid/unknown/present/withdrawn, never search behind head. Human cannot override knowncustomerfault/FMpresent/conflictingfacts/liveunreadablehistory/future/stale/missing/corrupt/textorigin/amount/oncekind. Business conflict no grant; return stable review_conflicts_with_evidence as validation_error detail or later blocked reason, not undefined public exception code.

Resolver allowlist `source://core/<table>/<encoded-pk>` orders/scans/attempts/compensation_ledger/external_events; `source://ops/<table>/<encoded-pk>` logs/alerts; metrics has encoded ts/service_id/metric three components. urllib.parse only, no HTTP/file fetch/SQL identifier from unvalidated string. Resolve exact run/identity/asof/aware availability, ownorder refs; global external/ops references need nonempty order-scope method note, human responsible substantive verification. Runtime evidence://ID only immutable sameorder/source/asof record; oldreview ID audit not authority. Unknownnamespace/table/malformed/future/crossorder -> validation_error, no writes. Store resolved structured facts/hash, not opaque ref strings; driver/ticket prose alone not proof.

Fingerprints common=sourceidentity/order/customer/guarantee/items/material fault/FM/terminal facts/proofapplicability; responsibility depends structured scans/attempts/callcounts, FM cited external/ops scope+note. Coins/voucher history fingerprint separately uses corresponding sourcekind rows+relevant unknown classification refs. Exclude unrelated rows/globaltick/timestamps that only represent checking; local ledgers checked live later, outside fingerprints. A coin runtime grant cannot invalidate voucher clearance. Sourcevoucher becomingvisible changes voucher history only. Materialfact/proofscope/sourcechange invalidates corresponding field; tick alone no refresh. Missing human resolution leaves FM unknown, no inferred absent from noalert/carrierfault.

Evidence payload exact spec5: history_by_kind two entries with classification/source_refs/reviewed_refs; selected_review null or **current head** ID/revision/common+perkind hashes. Build checks current assessment/sourcehealth and resolvable proof; activehead fields only when fingerprints fit, unknown/withdrawn no oldclearance. prepare as_of==now, contact/message both or neither, bindings/ownership; neither only orderauthorized cancel evidence with no entitlement signal. No caller eligibilityfields. Current pending/failed can record inbound messages; execution later blocks tick_unavailable. Prepare cannot promote stale assessment into current eligibility.
- [ ] **Step 4 — GREEN and shared positive fixture:** `python -m pytest acceptance_huy/test_task05_provenance.py acceptance_huy/test_task05_reviews.py -q`. Add voice/customer-opened/absentfalseerrorrule/foreignorder/IDcollision, received_atwall10:17+business10:00 noNext, materialchange invalidation, unrelatedtick reviewreuse, conflicting source proof rejection. Implement fixture `eligible(platform_factory) -> tuple[Platform,dict,str]` for later executor tests using real public recording/review/evidence, **no monkeypatch FM or executor**:

```python
def build_eligible_case(platform_factory):
    from platform_huy.dto import EligibilityReviewDecision
    from platform_huy.testing import T, actor, operator, FixtureRequestRule, seed_component_ready
    def seed(core, ops):
        core.execute("INSERT INTO external_events VALUES(?,?,?,?,?,?)", (
            "fm-proof", T.isoformat(), "weather", "P", "Fixture incident scope", "Test evidence"))
    p, kwargs = platform_factory(request_rule=FixtureRequestRule(), before_freeze=seed)
    seed_component_ready(p)  # labeled real SQLite prerequisite fixture; integration in Task 4
    p.record_contact_opened(contact_id="chat", order_id="o", channel="chat", proactive=True, opened_at=T, context=actor())
    p.record_customer_message(message_id="m", contact_id="chat", body="Tôi yêu cầu bồi thường do giao trễ", origin="text", received_at=T, context=actor())
    decision = EligibilityReviewDecision("carrier", "absent", "unknown", "unknown",
        (("responsibility", ("source://core/scan_events/e",)), ("force_majeure", ("source://core/external_events/fm-proof",))),
        (("responsibility", "Fixture operator checked the structured carrier-station loss."),
         ("force_majeure", "Fixture-only human determination: checked incident scope against this order; the cited event did not cover its route.")))
    p.record_eligibility_review("o", decision, expected_revision=0, reason="Fixture human verification", evidence_as_of=T, idempotency_key="review-r1", context=operator())
    ref = p.prepare_execution_evidence("o", as_of=T, contact_id="chat", message_id="m", context=actor())
    return p, kwargs, ref
```

Fixture proof/note models authorized human verification in isolated tests; cannot reuse this text as actual release verification. Register pytest fixture eligible calling helper above, finalize close. Staff must supply actual note/proof for realcase. Reviews fullreplacement fields unknown deliberately let independently-readable empty sourcehistory remain clear; no fake proof that unknown history is empty.
- [ ] **Step 5 — GATE:** clean review including reviewhead/fingerprint policy, controller commit `feat: record immediate chat provenance and audited eligibility revisions`, push huy.

Keep build_eligible_case and eligible fixture in `acceptance_huy/test_task05_provenance.py`; Task 6/7 tests explicitly import it without editing that file. Task-private fixture helpers stay in their own task tests. Task 5 components accept `gate_reader: Callable[[str], GateDecision]` and `assessment_reader: Callable[[str], OrderAssessment | None]` service-construction dependencies. Component fixture readers use explicit prerequisite SQLite rows, without replacing executor calls. Production controller binds Task 4 gate/view readers before exposing entitlement/proactive paths; absent bindings fail closed. No Task 3 import; literal prerequisite rows test component behavior before Task 4 validates actual current guard and publication.

### Task 6: Two independent local entitlements, transaction head revalidation

**Files:** Create `platform_huy/execution.py`, `acceptance_huy/test_task06_execution.py`. Controller wires facade/exports; no Task 7 cancellation.py or fixture edits.

**Policy gate:** Huy must resolve whether blocked attempts consume fixed canonical keys or only issued benefits lock those keys. Do not implement a guessed answer. Success receipt replay remains immutable.

**Interfaces:** Platform.execute_action/list_order_actions and module bind_platform/execute_action exact spec4. `semantic_hash(action: Action, context: ServerContext) -> str`; `authorize_source(action: Action, context: ServerContext) -> None`; `lookup_key` comes from Task 1 state.py; services compare returned metadata, never duplicate lookup; `has_local_grant(conn: sqlite3.Connection, order_id: str, kind: Literal["coins","voucher"]) -> bool`; `selected_review_matches(conn: sqlite3.Connection, order_id: str, prepared: dict | None) -> bool`. Test helper `benefit_action(ref: str, kind: Literal["coins","voucher"], *, key: str | None=None, amount: int | None=None) -> Action`, amount default11000/10000, sourcea1/rule, keys exactly xu:o/voucher:o for fixture order o, requested_at=T, callerqueue ignored.

- [ ] **Step 1 — RED independent amounts, grants and same-clock revocation.**

```python
def test_two_separate_actions_grant_two_kinds(eligible):
    from platform_huy.testing import actor, benefit_action
    p, kwargs, ref = eligible
    coins = p.execute_action(benefit_action(ref, "coins"), context=actor())
    voucher = p.execute_action(benefit_action(ref, "voucher"), context=actor("rule"))
    assert (coins.kind, coins.amount_xu, coins.amount_vnd, coins.voucher_ledger_id) == ("coins", 11000, None, None)
    assert (voucher.kind, voucher.amount_vnd, voucher.amount_xu, voucher.ledger_id) == ("voucher", 10000, None, None)
    assert p._connection.execute("SELECT COUNT(*),SUM(amount_xu) FROM ledger_new").fetchone() == (1, 11000)
    assert p._connection.execute("SELECT COUNT(*),SUM(face_value_vnd) FROM voucher_ledger").fetchone() == (1, 10000)
    assert p._connection.execute("SELECT COUNT(*) FROM action_receipts").fetchone()[0] == 2

def test_same_clock_withdrawal_blocks_first_execution(eligible):
    from platform_huy.testing import actor, operator, benefit_action
    p, kwargs, ref = eligible
    p.withdraw_eligibility_review("o", expected_revision=1, reason="Evidence withdrawn by staff",
        idempotency_key="withdraw-r2", context=operator())
    result = p.execute_action(benefit_action(ref, "coins"), context=actor())
    assert result.reason_codes == ("eligibility_review_changed",)
    assert result.decision == "blocked"
    assert p._connection.execute("SELECT COUNT(*) FROM ledger_new").fetchone()[0] == 0

def test_withdrawal_between_kinds_keeps_coin_receipt_but_blocks_voucher(eligible):
    from platform_huy.testing import actor, operator, benefit_action
    p, kwargs, ref = eligible
    action = benefit_action(ref, "coins")
    first = p.execute_action(action, context=actor())
    p.withdraw_eligibility_review("o", expected_revision=1, reason="Withdraw before second benefit",
        idempotency_key="withdraw-r2", context=operator())
    voucher = p.execute_action(benefit_action(ref, "voucher"), context=actor("rule"))
    replay = p.execute_action(action, context=actor())
    assert voucher.reason_codes == ("eligibility_review_changed",)
    assert replay.replayed is True and replay.ledger_id == first.ledger_id
    assert p._connection.execute("SELECT COUNT(*) FROM ledger_new").fetchone()[0] == 1
    assert p._connection.execute("SELECT COUNT(*) FROM voucher_ledger").fetchone()[0] == 0
```

- [ ] **Step 2 — RED:** `python -m pytest acceptance_huy/test_task06_execution.py -v`; exact two review-negative controls above must fail businessassert on stalehead implementation. No hidden forceunknown failure masking happy path.
- [ ] **Step 3 — implement source/capability/key/facts/effect pipeline inside one immediate transaction.**

```python
def authorize_source(action: Action, context: ServerContext) -> None:
    if action.source != context.source:
        raise PlatformError("permission_denied")
    if action.source not in ALLOWED_SOURCES[action.kind]:
        raise PlatformError("permission_denied")

def selected_review_matches(conn, order_id, prepared):
    head = review_head(conn, order_id)
    current = (head["review_id"], head["revision"]) if head else None
    bound = (prepared["review_id"], prepared["revision"]) if prepared else None
    return current == bound

def semantic_hash(action, context):
    payload = [context.principal_id, context.source, action.order_id, action.kind,
               action.amount_vnd, action.evidence_ref, action.confirmation_id]
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()
```

Validate Action shape/exactint not bool/float/negative, aware requested_at<=now; authority matching source/capability: actions:coins+a1, actions:voucher+rule, cancel:request+a1/app, localnotice contacts:write+a1; ownership server customer order. Refund/shippingrefund matrix valid cancel_reviewer returns policy_not_configured, no invented policy. Unauthorizedorder not_found, spoofpermission_denied before businessreceipt; A2/A3/LLM no entitlement capability. bind_platform once active run, mismatch/unboundvalidation_error, no client DB/run selector.

Inside writerlock re-read clock/version, sharednamespace key collision outbox/workflow/replay/reviews. Existing trusted samehash+principal receipt replay **before** any new review/facts re-evaluation; different semantic/order/kind/amount/evidence/principal/source -> idempotency_conflict, action_id keychanged conflict. Hash excludes action_id/requested_at/queue/needs_approval. Legacyoutbox no trustedreceipt blocked legacy_unverified; never infer success. Newrequest currentattemptsucceeded/currentassessment, else persist tick_unavailable denial audit without reserving a financial key. Compare prepared selectedreview ID/revision to currenthead **before** using clearance: changed -> blocked eligibility_review_changed, no fallback even materialhash same. Currentfingerprints/relevant fields invalid -> eligibility_review_required or underlying unknownreason, never stalehumanpermission. Reviewwriter uses same immediate serialization, cannot race between headcheck and INSERT.

Rebuild sourceidentity/asof/order/customer/contact/message/latestassessment/health live; evidencebindinginvalid blocked, text A1chat mintedrequest required for both kinds, else invalid_request_provenance. No futuredata/historicalhealthyboolean, financial_evidence_untrusted for sourcebad/conflict. LateVNcalendar delivereddate or now −guaranteed>=2, no status-onlylate rule. Knowncustomerfault customer_fault; FMpresent force_majeure; unresolvedFM force_majeure_unknown. Humanproof may resolve unknown only, never knownexclusion. No blanket proactive sticky/heartbeat ban on inbound entitlement, but attempt/source/currentassessment still required.

history_by_kind: sourcekind coins→coins, voucher→voucher, refund/shippingrefund consumes neither; unknown/malformedkind history_policy_unknown unless valid proof classifies relevant unknown, currentreadfailure history_unavailable cannot human-clear as empty. Separate local live ledger check by kind (has_local_grant), already_granted only thatkind; sourceknown grant cannot override. Coins recompute late_xu_for and exactquote; voucher exactly10000. Wrongintamount blocked amount_mismatch, malformedtypevalidation_error. Outbox serverqueue local_coins/local_voucher, receipt + respective ledger effect same transaction; for denied coins/voucher persist a structured execution-denied incident only: no outbox, action_receipts or ledger, and no canonical-key reservation. Successful grants alone insert outbox+receipt+effect. ExecutionResult correct null fields/noeffectIDs; no auto dualgrant, partialsuccess independent retries. eta_notice localintent only, cancellationTask7, no deliveryclaim.
- [ ] **Step 4 — GREEN:** `python -m pytest acceptance_huy/test_task06_execution.py -q`; quotes literal 239999→11000/None0→10000/20154000→1000000; voucher9999/bool/float denied, sourcea1voucher/appspoofrule denied. LateVN29→31=2 vs30=1; voice/inbound/FMpresent/customerfault/stalefinancial denied for both. Historicalvoucher blocks voucher only, coins viceversa, refund neither; unknownsourcekind ambiguity scoped. Two connections/same canonical key/same semantics onegrant+receipt replay; changed semantics conflict; UNIQUE(order_id) remains final duplicate guard; differentkinds both succeed. Fault aftereffect before receipt rollback, retry1; response lost/restart receiptimmutable afterwithdraw. All crossnamespace collisions conflict, no key overwrite. Coins first cannot invalidate voucher review/history. Noexternal effects.
- [ ] **Step 5 — GATE:** clean review especially two revocation oracles/perkindhistory, controller commit `feat: issue independent local coins and vouchers with live review checks`, push huy.

Produce `ExecutionService(platform).execute(action: Action, *, context: ServerContext) -> ExecutionResult` and `.list_order_actions(order_id: str, *, context: ServerContext) -> tuple[ExecutionResult,...]`. Task 7 owns cancellation request persistence; controller registers its handler after both handoffs. Task 6 never writes Task 7 files. Financial keys exactly xu:{order_id}/voucher:{order_id}; replace examples using arbitrary second same-kind keys with canonical-key duplicate/race cases. Same-kind UNIQUE(order_id) remains independent final guard.

### Task 7: Customer cancellation hai lượt và public recovery

**Files:** Create `platform_huy/cancellation.py`, `acceptance_huy/test_task07_cancellation.py`. Controller wires facade/cancel routing; do not edit execution.py or common fixtures.

**Interfaces:** Exact six Platform cancellation methods spec4 request/confirm/review/queue/get + execute_action(cancel_request). `CancellationService(platform: Platform)` handles shared persistence; `order_snapshot_hash(projection: Projection, order_id: str) -> str` canonical visible cancellation/terminal logistics facts; getters current workflow, immutable request receipt separate.

- [ ] **Step 1 — RED request→restart→own getter→confirm, no reviewer privilege.**

```python
def test_action_cancel_recovery_does_not_require_review_queue(platform_factory):
    import pytest
    from contracts.types import Action
    from platform_huy.dto import PlatformError
    from platform_huy.platform import Platform
    from platform_huy.cancellation import CancellationService
    from platform_huy.testing import T, actor, operator, seed_component_ready
    customer = actor("app")
    p, kwargs = platform_factory()
    seed_component_ready(p)  # component prerequisites only; integrated public APIs in Task 4
    ref = p.prepare_execution_evidence("o", as_of=T, context=customer)
    action = Action("cancel-act", "o", "cancel_request", 0, "app", T, "request-key", ref, False, "caller-bypass")
    initial = CancellationService(p).request_action(action, context=customer)
    p.close()
    resumed = Platform(**kwargs)
    receipt = CancellationService(resumed).request_action(action, context=customer)
    assert receipt.cancel_id == initial.cancel_id and receipt.replayed is True
    state = resumed.get_cancellation(receipt.cancel_id, context=customer)
    assert (state.status, state.version) == ("awaiting_confirmation", 1)
    confirmed = resumed.confirm_cancellation(state.cancel_id, state.confirmation_id,
        expected_version=1, idempotency_key="confirm", context=customer)
    assert (confirmed.status, confirmed.version) == ("awaiting_review", 2)
    assert resumed.get_cancellation(state.cancel_id, context=customer).version == 2
    with pytest.raises(PlatformError) as error:
        resumed.list_review_queue(context=customer)
    assert error.value.code == "permission_denied"
    assert resumed._connection.execute("SELECT COUNT(*) FROM ledger_new").fetchone()[0] == 0
    assert resumed._connection.execute("SELECT COUNT(*) FROM voucher_ledger").fetchone()[0] == 0
    resumed.close()
```

- [ ] **Step 2 — RED:** `python -m pytest acceptance_huy/test_task07_cancellation.py -v`; expected recovery/reference/version assertions FAIL before workflow implementation.
- [ ] **Step 3 — implement request+confirm+review under shared key writerlock.** Owncustomer app/delegatedA1 cancel:request creates cancel_id/new randomconfirmation_id version1 awaiting_confirmation, amount0, serverqueue cancel_review/needsapprovaltrue; ignores caller bypassfields. Dedicated request and Action same persistence. Dedicated retry lookup original ownsource/order key/receipt before minting evidence so same key doesn't drift; mismatch principal/order/source conflict. Dedicated retry returns original v1 receipt/replayedTrue; getter currentversion. No request auto consumes confirmation.

```python
def next_cancel_state(status: str, command: str, decision: str | None = None) -> tuple[str,int]:
    if status == "awaiting_confirmation" and command == "confirm":
        return "awaiting_review", 2
    if status == "awaiting_review" and command == "review" and decision in ("approve", "reject"):
        return ("approved" if decision == "approve" else "rejected"), 3
    raise PlatformError("version_conflict")
```

Confirm owncustomer+cancel:confirm, exacttoken/order/customer/expectedversion1 + currentmaterialsnapshot unchanged; update WHERE version/status, rowcount1, persist workflowcommand result atomically. ID not bearer secret, wrongcustomer not_found; wrongtoken/version/materialchange/consumednewkey version_conflict. Samekeycommand retry before consumed/version checks returns storedresult; keychanged payload/principal/cancelID/operation conflict across all namespaces. Reviewer sourcecancel_reviewer+cancel:review/nonemptyreason/expected2, current snapshot check, v3 approved/rejected only localworkflow, no refund/entitlement/sourceupdate/carrierclaim. Getter cancel:read own/delegated or authorized reviewer; queue only reviewer, no customerqueue access. Sameconfirmation two connections onev2/oneversionconflict, no TTL. Inbound cancellation available failedattempt; sourcefacts unsafely unreadable failclosed, no blanket proactive gate.
- [ ] **Step 4 — GREEN:** `python -m pytest acceptance_huy/test_task07_cancellation.py acceptance_huy/test_task06_execution.py -q`; literal v1/v2/v3, foreignownership, replayafterreview originalrequestreceipt + currentgetterv3, staleversion/wrongtoken/secondkey consumed/conflictingkeys, sourcehash unchanged and bothledger0. Real separate customer affirmative turn remains Trúc integration requirement, no mock claim.
- [ ] **Step 5 — GATE:** clean review, controller commit `feat: add recoverable two-step runtime cancellation`, push huy.

### Task 8: Seller-visible return signal và integration labels

**Files:** Create `platform_huy/return_history.py`, `acceptance_huy/test_task08_return_history.py`. Controller wires getter. README is Task 9 only.

**Interfaces:** `ReturnHistory(platform: Platform).get(order_id: str, *, as_of: datetime, context: ServerContext) -> ReturnHistorySignal`; facade exact spec4. Customer/seller resolved internally from viewed order, no caller customer selector.

- [ ] **Step 1 — RED separate request/order/physical counts and window.**

```python
def test_return_requests_are_not_physical_returns(platform_factory):
    from platform_huy.testing import T, actor, operator
    def seed(core, ops):
        core.executemany("INSERT INTO returns VALUES(?,?,?,?,?,?,?)", [
            ("r1", "o", "2026-10-30T20:00:00+07:00", "fake", "refunded", "2026-11-01T00:00:00+07:00", 100000),
            ("r2", "o", "2026-10-30T21:00:00+07:00", "damaged", "requested", None, None),
            ("future", "o", "2026-11-01T00:00:00+07:00", "damaged", "requested", None, None)])
        core.execute("INSERT INTO scan_events VALUES(?,?,?,?,?,?,?,?)", (
            "returned", "o", "returned", "station", "st", T.isoformat(), T.isoformat(), None))
    p, kwargs = platform_factory(before_freeze=seed)
    p.initialize_tick(idempotency_key="init", context=operator())
    seller = actor(None, customer_id=None, seller_id="s", capabilities=frozenset({"returns:read"}))
    signal = p.get_return_history_signal("o", as_of=T, context=seller)
    assert (signal.visible_request_count, signal.visible_order_count_with_requests, signal.physical_returned_order_count) == (2, 1, 1)
    assert (signal.review_required, signal.threshold_policy, signal.unknown_link_count) == (None, None, 0)
    assert (signal.coverage_complete, signal.status_history_available) == (False, False)
    assert set(signal.evidence_refs) == {"returns:r1", "returns:r2", "scan_events:returned"}
    assert signal.window_start.isoformat() == "2026-10-17T17:00:00+00:00"
    assert signal.window_end == T
```

- [ ] **Step 2 — RED:** `python -m pytest acceptance_huy/test_task08_return_history.py -v`; expected distinctcounts/window/coverage assertions FAIL.
- [ ] **Step 3 — implement authorization before aggregation.** Need returns:read + seller matches ownvisible viewedorder; resolve customer. Require coverage_start<=as_of<=currentmanualnow, aware; historicalread doesn't authorizecontact/money. Candidates samecustomer/seller and orders.created<=asof, returns.requested<=asof. Requests countreturn IDs, orders DISTINCT separate; physical DISTINCTorder returned scan event<=ingest<=asof independent of requestrow. returning/return_failed/cancelled not physical. Ref stabletable:ID, no rawstatus/refundfuture/body/names/phone/address.

```python
request_ids = {row["return_id"] for row in scoped_returns}
request_orders = {row["order_id"] for row in scoped_returns}
physical_orders = {row["order_id"] for row in scoped_scans if row["status"] == "returned"
    and datetime.fromisoformat(row["event_at"]) <= datetime.fromisoformat(row["ingested_at"]) <= as_of}
counts = len(request_ids), len(request_orders), len(physical_orders)
```

SourceIdentity windowstart, not observedmin/lookback invented; observedvalidrequested min/max nullable, coverage/statushistory false. Knownscope malformed/missinglink unknown_link_count++, exclude invalidrequest; impossible sellerscope only internalincident, not shop leak. Schema/queryerror source_invalid no countzero fallback. review_required/threshold_policy alwaysNone even highcounts. Never feed this signal into fault/eligibility/cancel. Labels “yêu cầu trả”/“đơn có yêu cầu”/“đơn có scan đã trả”, no summed “lần hoàn”.
- [ ] **Step 4 — GREEN:** `python -m pytest acceptance_huy/test_task08_return_history.py -q`; future request/order hidden, ownother seller not_found, knownscope missingidentity unknowncount, sourceerror not zero, physicalscanwithoutrequest1, duplicate scans sameorder1, canceled/returning/failed0. Highcount fixture stays None/None with unchanged entitlement decision; do not claim repeatedreturns realcase—the release max ownshopcustomer is1.
- [ ] **Step 5 — GATE:** clean review, controller commit `feat: expose scoped return evidence without fraud decisions`, push huy.

### Task 9: Huy demo adapter, independent oracles và honest handoff

**Files:** Create `platform_huy/demo.py`, `platform_huy/recovery.py`, `acceptance_huy/test_task09_demo.py`, `acceptance_huy/test_task09_independent_oracles.py`, .scratch/specs/2026-10-31-huy-platform-verification.md and .scratch/specs/2026-10-31-huy-a1-handoff.md; update platform_huy/README.md. Verification logs/mutation copies stay in .scratch/runs/task-09; actual runtime/fixture state stays in unique runs roots.

**Interfaces:** `demo.main(argv: list[str] | None=None) -> int`, `open_demo(run_id: str, start_at: datetime | None) -> Platform` source paths fixed read-only, state runs/run_id; `load_review(path: Path) -> tuple[EligibilityReviewDecision,str]` strict JSON fourfields/refs/notes/reason from **actual staff file**, no defaults. CLI operator context localtrusted staff; issue-kind context derived by server wiring and saved authenticated contact/order/message, not clientsource JSON. No HTTP/authframework, A1 classifier or network. Huy adapter exercises platform APIs, cannot manufacture real Trúc A1 integration.

- [ ] **Step 1 — fresh reviewer derives independent literal oracles before implementation narrative.** Write tests for source age/event-vs-ingestion, sameclockreviewwithdrawal and coin-beforewithdraw/voucherblocked, currentguard after A2fail, independent benefits and namespacecollisions. CLI RED test parse `show` read-only/no clockadvance, `next` stablekey exactly+30; missing real saved A1provenance issue exits nonzero with no entitlement. Actual CLI calls main through argparse; no mocking executor to success.

```python
def test_ingestion_does_not_refresh_source_age(source_files):
    from datetime import datetime
    from platform_huy.testing import seed_base, T
    from platform_huy.sources import Sources
    from platform_huy.replay import project
    from platform_huy.guard import health_for
    seed_base(source_files.core, 239999)
    source_files.core.execute("UPDATE scan_events SET event_at='2026-10-30T23:00:00+07:00' WHERE event_id='e'")
    core, ops = source_files.freeze()
    src = Sources(core, ops)
    src.validate()
    health = {h.feed: h for h in health_for(project(src, tick_at=T, previous_watermark=None), tick_at=T)}
    assert health["scan_events"].source_timestamp == datetime.fromisoformat("2026-10-30T23:00:00+07:00")
    assert health["scan_events"].last_ingested_at == T
    assert health["scan_events"].status == "stale"
    src.close()
```

Additional actual CLI RED/GREEN recovery oracle: issue coins with xu:o using real executor, lose response, close/reopen, withdraw review or NEXT, repeat same CLI args/key/contact/message. Assert original effect ID/receipt and exactly one coins row, zero new evidence minted. A new voucher:o request after withdrawal checks current authority and is blocked. Changed contact/message/amount under existing key conflicts. Test via argparse main, not mocked executor success.

- [ ] **Step 2 — RED:** `python -m pytest acceptance_huy/test_task09_demo.py acceptance_huy/test_task09_independent_oracles.py -v`; expected CLI/noadvance/oracle assertions FAIL before adapter. Staffproof rejection must remain denial, not be changed to happyexpected.
- [ ] **Step 3 — implement small argparse adapter and real-source walkthrough.** Commands initialize/next/retry/show/review/withdraw/request-info/issue-kind/cancel-request/cancel-confirm/cancel-review/returns. Each command calls exactly documented Platform API, prints canonical DTO JSON, exit0 only successful operation/read, businessblocked output exit1, validation/permission/storage error exit2. Show no clockadvance; next requires expectedversion+key; retry sameattempt. Run_id sanitize single directory component, persist start/config identity; subsequent commands load existing start, no wallclock default. `review --file` requires actual staffproof JSON, maps allfourfields, expectedrevision, reasontoaudit. No generated note/approve-all. `request-info` only finds already recorded A1-opened authenticated textsignal for ownorder; missing emits `a1_provenance_required` CLI reason/no fabricated contact. issue-kind uses actual contact/message IDs and derives exact canonical key xu:{order_id} or voucher:{order_id}; explicit --key must match. FIRST call `recover_action(key: str, *, order_id: str, kind: Literal["coins","voucher"], contact_id: str, message_id: str, context: ServerContext) -> Action | None` in Task 9 recovery.py. It uses Task 1 lookup metadata plus authoritative stored outbox/action_receipts/execution_evidence, requires actions:read and original principal/source/order/kind/contact/message bindings, reconstructs and returns the exact original Action/evidence_ref/amount without invoking the executor. The CLI caller invokes the real executor exactly once with that returned Action. Never prepare new evidence under an existing key, weaken semantic hash or invent trusted legacy success. Only absent key prepares current evidence/new Action. Changed amount/contact/message/principal/source conflicts. Pending blocked-key answer governs blocked records; successful receipts replay unchanged after NEXT/review withdrawal. No auto-otherkind.

```powershell
python -m platform_huy.demo --run-id demo-late --start-at 2026-10-24T15:30:00+07:00 initialize --key init
python -m platform_huy.demo --run-id demo-late show --order-id 261021ZS7E76FW
python -m platform_huy.demo --run-id demo-late next --expected-version 1 --key next-1600
python -m platform_huy.demo --run-id demo-late show --order-id 261021ZS7E76FW
```

At15:30 deliveredscan EV000067934 hidden; at16:00 visible event15:36:47/ingest15:36:48, guarantee22/10/value525000. Assert facts before considering grant; conditional **26000 xu +10000 VND** only if sourcevalidation/currentattempt/provenance/actualstaffverification/history allpass. No IDhardcode eligibility. Staff prepares own JSON file `runs/demo-late/staff-review.json` after examining actual allowedrefs (orders/citedscan/attempt/appropriateexternalorops proof); adapter validates existence/shape/resolvability, does not create it. README requires actual method/scope note for responsibility and FM, not “delivered therefore absent”. Missing actual note/proof means report blocked eligibility_review_required/force_majeure_unknown, not invent success.

```powershell
python -m platform_huy.demo --run-id demo-late review --order-id 261021ZS7E76FW --expected-revision 0 --key verified-r1 --file runs/demo-late/staff-review.json
$request = python -m platform_huy.demo --run-id demo-late request-info --order-id 261021ZS7E76FW | ConvertFrom-Json
python -m platform_huy.demo --run-id demo-late issue-kind --order-id 261021ZS7E76FW --kind coins --contact-id $request.contact_id --message-id $request.message_id --key xu:261021ZS7E76FW
python -m platform_huy.demo --run-id demo-late issue-kind --order-id 261021ZS7E76FW --kind voucher --contact-id $request.contact_id --message-id $request.message_id --key voucher:261021ZS7E76FW
```

Run issue commands only after request-info exit0 from real Trúc adapter input. If A1 absent, stop this positive path with named dependency, continue D0/D1/D2/D3 Pythonfoundation walkthrough; isolated fixture tests verify implementation but are labeled fixtures. Demonstrate manual fault with test faultinjection only, not source edits, keeps actualA3/oldA2/deny view; do not add production failure switch. Cancel requester firstresult getter supplies actual cancelid/token/version to separate confirmcommand; reviewer then approves localworkflow, source/ledgers unchanged. Returns actual case separate run start2026-10-27T04:30+07 Next05:00, order261023TDK6SMSY ownshopSH2463399: literal request/order/physical0/0/0→1/1/0, futuredecidedstatus/refundmasked. No repeatedreturn story. Delayedscan case Oct19 19:00→19:30 EV000410037 newlyvisible while eventprogress remains later sortingcenter; no new worldrows.

- [ ] **Step 4 — mutation-negative controls on independent scratch snapshots.** Freshprocess cwd/PYTHONPATH snapshot, baseline GREEN first, only Huyowned code mutate, source DBs never copied into mutable path. Fixture state root snapshot/runs ensures QuestionStore. Each mutation starts clean snapshot, tests/expected unchanged; script helper uses literal once-replacement or AST-identified exact functionbody and parsecheck, mismatch is harnesserror:

```python
def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (path, "mutation target mismatch")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

replace_once(snapshot / "platform_huy/guard.py", "now-source_at > timedelta(minutes=30)", "now-source_at >= timedelta(minutes=30)")
result = subprocess.run([sys.executable, "-m", "pytest", "acceptance_huy/test_task04_guard.py", "-q"], cwd=snapshot, text=True, capture_output=True)
assert result.returncode == 1
assert "test_source_age_boundary" in result.stdout and "AssertionError" in result.stdout
assert "ERROR collecting" not in result.stdout
```

Mutation matrix: >30→>=30; SOURCE_FIELDS scan event_at→ingested_at; has_local_grant forcedFalse plus only relevantledgerorder UNIQUE removed in scratchschema to expose business duplicate; authorize_source binding bypass; signal origin textcheck bypass; **selected_review_matches forcedTrue** run both named Task6 withdrawal tests and require reason/state businessassert failure. For the last mutant report actual failure (e.g. wrongreason vs accidentalgrant), do not claim effect that didn't occur. Also mutate headselector to latestactiveverified fallback and require r2unknown/r3withdrawhead tests fail. Reviewer verifies exactdelta once and ASTsyntax before run; returncode1+assert/DIDNOTRAISE required, import/setup/timeout not killedmutant. Never weaken owner tests or mutate livecheckout/source. If refactor changed literal, locate equivalent Huy function and record exact diff, not silently skip.
- [ ] **Step 5 — GREEN/fullcheck and final broad review/GATE.** `python -c "import contracts; import logistics_an_nguyen.models"`; reverseimport freshprocess; `python -m pytest --collect-only -q`; `python -m pytest -q -rA`; controller `git diff --check`. Log actual revision/commands/collected/pass/fail/skip/xfail/exit, both sourcehashes before/after realreadonlydemo, concurrency/restart evidence and mutation businessfailures. Exit5/missingtest/skip not pass. Cleanfinalreview spec+quality+R1–R11; controller commit `test: add Huy demo adapter and independent platform verification`, push huy. Receipts persist in verification doc before SDD workspace cleanup.

Handoff document lists actual callable seams, not promised implementation: Trúc deterministic versioned requestadapter/authenticatedorigin/realcontactevent, 7intents/rules-beforeLLM/template facts-amount-date-promise validator, human/threeabusive turnshandoff persistence, separate affirmativecancelturn, actual transport currentgate before send, Pythonview/manualoperator APIs, sourcebound a1/rule separate calls, partialsuccess retry. acceptance_truc remains **pending real A1 seam**, no fake executor/skip to call it verified. Localissuance success never externalwallet/provider/voucherredemption/expiry claim; positive releasecase still requires actual staffnote and actualcustomertext.

## Coverage và self-review

| Spec requirement | Tasks / decisive evidence |
| --- | --- |
| R1 immutable sources | 1,2,9: ro/query_only/manifest/unchanged hashes, runtime separate |
| R2 as-of/time | 2,3,5,8: complete ingestiongroup/masks/manualnow/servermessageclock |
| R3 validation | 2,3,4: visiblecorrupt global, futureisolation, unsafe failure durable |
| R4 A3 | 3,4,9: source30/heartbeat60, stickyonlytighten, currentguard afterA2fail |
| R5 stages/tick | 1,3,4: clockattempt durable/A3 owncommit/A2 atomic/progress fresh |
| R6 authority | 5,6,7: capability/source/ownership/service-minted signals, sharedgate |
| R7 both benefits/review | 5,6,9: fullreplacement revisions/perkinddeps/livehead/actualproof |
| R8 atomicity/idempotency | 1,3,5,6,7: sharedkeynamespace/twoledgers/crash/concurrency/immutable retry |
| R9 cancellation | 7,9: separate confirm/reviewer/currentgetter/sourceunchanged |
| R10 returns | 2,8,9: scopedthreecounts/coverage/no thresholds/no fake repeatedcase |
| R11 independent checks | every RED/GREEN/GATE; 9 cleanoracle/mutations/honestlimits |

Plan self-review: no production/source/test changes performed here; snippets are implementation guidance, all commands planned. DTOs/public signatures anchored in finalspec4, new message received_at and manual clock correctly replace oldv1clock. Helpers' producers/consumers declared; no A2runtimeimports in contracts. Exact reviewhead ID/revision compare and writer serialization prevent sameclock staleclearance; immutable receipt replay precedes re-evaluation. CurrentGuard and StoredTick retain separate meanings and consistentread. Known perkindhistory doesn't consume anotherbenefit; unknownhumanproof does not bypass knownexclusion/livehealth/provenance. Pending blocked-key answer explicitly gated; unforeseen ambiguity asks Huy before affectedimplementation. Ready for independent plan review, not a claim that implementation or wholeprojectdemo has passed.


### Task 6 confirmed denial/retry test addition

Use the design final section success-only reservation rule. Before implementation, save actual RED for a denied request followed by authorized human verification, fresh evidence and retry using the SAME canonical key. Literal expected transition: audit1/outbox0/receipt0/ledger0 -> audit1/outbox1/receipt1/ledger1 -> retry same original effect/ledger1. Cover coins and voucher separately. Denial audit uses existing incidents structured evidence; no Task 1 schema or other task files are modified. list_order_actions must preserve prior denied result and successful receipt for the authorized own order. Task 9 only recovers original Action from a successful reserved key; denial-only history permits preparing new current evidence.
