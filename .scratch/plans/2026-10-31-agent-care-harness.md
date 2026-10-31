# Agent Care Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Xây runtime A1 chat có rules trước model, lưu bền mỗi lượt, gửi effect sau commit và phục hồi được mà không lặp quyền nghiệp vụ.

**Architecture:** `CareHarness` điều phối một lượt cố định; `CarePolicy` thuần trả state dự kiến và proposal. SQLite riêng là nguồn state, request budgets và durable effects; dispatcher claim trước network và đối soát receipt theo stable key. Platform cấp trusted context, gate, evidence resolver và gateways; test adapters chỉ nằm trong tests.

**Tech Stack:** Python 3.11+, asyncio, sqlite3, dataclasses, typing.Protocol, standard library và pytest hiện có; không thêm SDK/framework/dependency.

**Spec:** [Harness](../specs/2026-10-31-agent-care-harness.md); [nghiệp vụ A1](../specs/2026-10-31-agent-care.md). Đọc cả hai trước triển khai. AGENTS.md, docs/team_plan.md, docs/decisions.md và contracts luôn có ưu tiên cao hơn.

## Global Constraints

- Đây là plan, không phải bằng chứng runtime đã chạy hoặc phê duyệt mọi đề xuất của hai spec. Duyệt plan trước implementation; protocols platform cần Huy duyệt trước ghép HTTP hoặc gửi thật.
- Python 3.11+, standard library và pytest đang có. Lõi không phụ thuộc SDK model hoặc workflow framework.
- Chỉ sửa `care_truc/` khi thực thi. Không đổi contracts, dependencies, platform, acceptance_truc hoặc nguồn release DB; không cài Git hooks.
- State tại `runs/<run_id>/care.sqlite`; không track DB, data, runs, truth, .env hoặc index CodeGraph.
- Không copy Action, OrderAssessment, ContactTask, enum hoặc params. Dùng `contracts.params.max_turns` (8), `late_xu_for`, feed 30 phút và heartbeat 60 phút.
- Lượt khách: tối đa 8; lượt thứ 8 handoff. Abuse: 3 lượt khác nhau. Mở phiên/lời mở đầu không tăng lượt. Message, confirm và handoff dùng chung request namespace.
- Text mỗi message: 4.000 Unicode code points, không cắt trước intent. Model context: 12.000 UTF-8 bytes sau serialize, tối đa 4 lượt gần nhất; output: 2.048 UTF-8 bytes.
- Model: 1 attempt/lượt kể cả restart, timeout 3 giây. Context/gateway: 2 giây/call. Hooks: tổng 100 ms/phase. Adapter phải hỗ trợ deadline/cancellation.
- Processing: tối đa 3 lần trước final commit. Submission: tối đa 3 calls có thể ra ngoài. Lookup: tối đa 3 calls tự động liên tiếp không có kết quả có thẩm quyền. Backoff vận hành 1 giây rồi 5 giây.
- Drain: tối đa 20 effects hoặc 2 giây để bắt đầu effect mới; call đang chạy có timeout riêng. Shutdown chờ tối đa 5 giây.
- Assessment tuổi tối đa 30 phút, confirmation TTL 10 phút theo business clock. Ngưỡng feed/heartbeat chỉ chặn khi vượt 30/60 phút; timestamp tương lai luôn bị chặn.
- UTC có timezone cho nghiệp vụ do platform cấp; monotonic/deadline cho vận hành. Không dùng replay cutoff để chạy timeout/backoff.
- A1 không thực thi tiền. Xu cần yêu cầu text hiện tại trong chat A1 mở, contact thực sự sent, late_days >= 2, fault carrier/platform, facts hợp lệ và chưa grant/pending; voice và typed confirm không cấp quyền D4.

## Review Focus

1. Replay clock nhảy, process restart đổi monotonic origin: deadline vận hành không chạy theo replay hoặc bị reset budget (Tasks 1, 3, 9).
2. Khách khác retry request đã cache: kiểm quyền trước dedup/read, không lộ response/evidence (Tasks 6, 10).
3. Hooks giữ nested mutable objects hoặc callback muộn: không thay identity/facts, không ghi sau fallback/boot mới (Tasks 5, 6, 9).
4. Hai session cùng order đua revision/coins key: chỉ một revision được claim, attempt đã reserve đóng băng payload (Tasks 3, 7).
5. Receipt revision trùng nhưng khác nội dung hoặc terminal mâu thuẫn: báo adapter error, giữ trạng thái đã biết và không tạo event lặp (Task 8).

## Hiện trạng và tổ chức file

Tại lúc khảo sát, `care_truc/` chỉ có README; chưa có policy, harness hoặc server A1. Branch hiện tại `truc/care-harness`. Các tên sau là interface mới, không phải API đã tồn tại. CodeGraph ban đầu chưa initialized; không suy diễn rằng server platform đã cung cấp adapters.

| File mới | Trách nhiệm |
| --- | --- |
| `care_truc/__init__.py` | Exports hẹp của harness |
| `care_truc/runtime_types.py` | Frozen runtime records, tagged results và budgets |
| `care_truc/ports.py` | Context, clock, model, gateway, gate và evidence protocols |
| `care_truc/schema.sql` | 8 nhóm bảng trong spec và evidence bundles |
| `care_truc/store.py` | Connection/transactions, request/event/state persistence |
| `care_truc/effect_store.py` | SQL effect revisions/claims/receipts, chỉ được MemoryStore gọi |
| `care_truc/process_lock.py` | OS lock cho run trên Windows/POSIX |
| `care_truc/policy.py` | Intent/rules, counters, confirmation và eligibility thuần |
| `care_truc/guardrails.py` | Input/context/proposal/output/dispatch validation |
| `care_truc/phrases.py` | Catalog phrase IDs và model context serialization |
| `care_truc/renderer.py` | Render facts và handoff summary bằng code |
| `care_truc/hooks.py` | Registry bất biến và phase hook execution |
| `care_truc/harness.py` | Ingress, session locks, owner registry và final commit |
| `care_truc/dispatcher.py` | Gate, claim, submit, lookup, backoff |
| `care_truc/lifecycle.py` | Startup/recover/shutdown/health |
| `care_truc/api.py` | Adapter JSON in-process, không sở hữu HTTP server |
| `care_truc/tests/` | Fixtures, fake adapters và tests bên dưới |

Giữ đây là một plan vì loop/transaction/claim/recovery cùng bảo vệ một invariant xuyên suốt. Mỗi task là một unit có thể review và test riêng; Task 10 chỉ ghép API sau khi lõi an toàn.

## Cách chạy từng unit

Trước implementation và trước push: `git fetch origin`, kiểm thay đổi remote feature nếu có, merge nhánh feature remote tương ứng rồi `git merge origin/main`; bảo toàn local changes. Không thực hiện Git integration chỉ để viết tài liệu này. Không merge main ngược lại hoặc push main.

Tests async dùng `asyncio.run()` từ pytest sync, không thêm pytest-asyncio. Test dùng Event/barrier và fake clock thay sleep thật; subprocess lock tests dùng timeout hữu hạn. Mỗi task theo chu kỳ RED → minimal implementation → GREEN → commit. Trước commit/push chạy import contracts, toàn bộ pytest, diff check và guardrails ở Task 11; push từng unit đã verified tới `origin truc/care-harness` sau fetch/merge và chạy lại checks nếu có thay đổi. Không force push.

### Task 1: Runtime records, protocols và test adapters

**Files:** Create `care_truc/{__init__,runtime_types,ports}.py`, `care_truc/tests/{__init__,helpers,test_runtime_types}.py`.

**Interfaces:**
- `TrustedRequestContext(principal_id: str, staff_permissions: frozenset[str])` do server dựng; ownership phải tra qua port, không tin field client.
- Frozen `CustomerEvent(kind: Literal['message','confirm_cancel','request_handoff'], request_id: str, text: str | None, reply_to: str | None, confirmation_id: str | None)`.
- Frozen `SessionState`, `ContextSnapshot`, `PolicyOutcome`, `EffectProposal`, `Receipt`, `TurnResult`, `Health`, `DrainReport`; giữ nguyên contract Action trong proposal.
- `ContextProvider.authorize(ctx, order_id) -> None`, `load(ctx, order_id) -> ContextSnapshot` async; snapshot gồm cutoff, assessment nguyên khối, principal/order binding, items_value, contact sent receipt, ledger state, guard và server feed policy.
- `PhraseSelector.select(context: bytes, *, deadline: float) -> bytes`; `DispatchGate.check(proposal, ctx, *, deadline) -> GateDecision`; `EffectGateway.submit(proposal, *, deadline) -> Receipt`, `lookup(key, *, deadline) -> Receipt | None` async. Gateway khai báo idempotent/deadline capabilities. Gate nguyên tử tại gateway vẫn là trách nhiệm platform.
- `EvidenceResolver.resolve(ref: str, server_ctx) -> EvidenceBundle` async; expose theo quyền server, không endpoint khách.
- `RuntimeClock.monotonic() -> float`, `utcnow() -> datetime`, `wait_until(deadline: float) -> Awaitable[None]`. Persist retry due theo operational UTC, rebase remaining delay về monotonic khi boot; không persist monotonic tuyệt đối giữa boots.

- [x] Viết `test_shared_types_are_reused`, `test_untrusted_payload_cannot_build_trusted_context`, `test_clock_is_independent_of_replay`: assert contract identity, schema reject source/role/cutoff/amount/proactive/guard_allowed, fake replay nhảy một ngày không hết deadline vận hành.
- [x] Chạy `pytest -q care_truc/tests/test_runtime_types.py`; RED do modules chưa tồn tại.
- [x] Định nghĩa records/protocols trên, đầy đủ fields spec §§4,7,10,12; dùng immutable nested tuples/records hoặc defensive deep copies. Helpers gồm fixed trusted context, FakeClock, ScriptedGateway, BlockingSelector và fault-injectable store; không có production defaults.
- [x] Chạy lại command, expect PASS; commit `feat(care): define runtime ports and deterministic fixtures`.

### Task 2: SQLite memory, atomic turn và process lock

**Files:** Create `care_truc/{schema.sql,store.py,process_lock.py}`, `care_truc/tests/test_memory.py`, `care_truc/tests/test_process_lock.py`.

**Interfaces:** `MemoryStore.open(path: Path) -> MemoryStore`, `load_session(id) -> SessionState`, `begin_request(session_id, principal_id, event, fingerprint) -> RequestRecord`, `commit_turn(request_id, expected_version, outcome, response, evidence, trace) -> TurnResult`, `close() -> None`; sync methods chỉ short transactions trong event-loop thread. `RunLock.acquire(run_dir: Path) -> RunLock`, `release() -> None`.

- [x] Viết tests `test_turn_commit_is_atomic`, `test_commit_failure_rolls_back_everything`, `test_reopen_preserves_confirmation_and_events`: assert response/counters/state version/evidence/effects commit cùng nhau, crash trước commit không tăng lượt; sequence không trùng và lịch sử append-only.
- [x] Thêm `test_corrupt_or_future_schema_is_not_reset`, `test_second_process_same_run_fails`, `test_process_death_releases_lock`; checksum DB lỗi trước/sau không đổi, process khác run vẫn mở được.
- [x] Chạy `pytest -q care_truc/tests/test_memory.py care_truc/tests/test_process_lock.py`; expect RED.
- [x] Implement schema version 1 với runtime_meta, sessions, requests, events, pending_effects, effect_proposals, effect_attempts, receipts và evidence_bundles. Requests UNIQUE(run, principal, session, request_id), events UNIQUE(session, sequence), effect key UNIQUE(run,key); lưu request kind trong fingerprint cùng payload canonical. Check schema/integrity trước writes, unsupported/corrupt fail closed. OS lock dùng `msvcrt.locking` Windows hoặc `fcntl.flock` POSIX, giữ handle tới close; run_id phải là một path segment an toàn.
- [x] Chạy lại tests, expect PASS; commit `feat(care): persist atomic turns with exclusive run ownership`.

### Task 3: Durable budgets và effect revisions

**Files:** Modify `care_truc/store.py`, create `care_truc/effect_store.py`, `care_truc/tests/test_durable_budgets.py`.

**Interfaces:** `MemoryStore.reserve_processing(request_id, boot_generation) -> AttemptToken`, `reserve_model(request_id) -> AttemptToken | None`, `revise_proposal(effect_key, source_request, proposal) -> int`, `claim_effect(effect_id, expected_session_version, expected_revision) -> ClaimedEffect | None`, `record_receipt(receipt) -> bool`. Tokens chứa request/state version/boot generation; effect claim commit budget và attempt trước trả về.

- [x] Viết tests `test_model_reservation_survives_restart` (attempt <= 1), `test_processing_budget_survives_restart` (attempt <= 3, backoff 1/5 giây), `test_coins_key_unique_across_sessions`, `test_unsent_revision_append_only`, `test_first_claim_freezes_payload`, `test_stale_version_or_revision_cannot_claim`.
- [x] Chạy `pytest -q care_truc/tests/test_durable_budgets.py`; expect RED.
- [x] Implement counters lưu bền trước work; lỗi lưu counter không bắt đầu work. Key canonical từ contact.idempotency_key, run/order coins, pending confirmation cancel và run/session handoff. Revision chỉ từ explicit customer text request với context hợp lệ, trước mọi outbound attempt; transaction effect key serialize hai session. Dùng DB compare-and-update session version/revision khi claim.
- [x] Chạy lại tests, expect PASS; commit `feat(care): enforce durable attempt budgets and effect revisions`.

### Task 4: Policy thuần, renderer và core guardrails

**Files:** Create `care_truc/{policy,guardrails,renderer,phrases}.py`, `care_truc/tests/test_policy.py`, `care_truc/tests/test_guards.py`.

**Interfaces:** `CarePolicy.evaluate(state: SessionState, event: CustomerEvent, context: ContextSnapshot) -> PolicyOutcome`; `ResponseRenderer.render(outcome, context, phrase_id: str) -> RenderedResponse`; `render_handoff(state, context) -> HandoffSummary`; `Guardrails.validate_context(snapshot) -> GuardDecision`, `validate_output(rendered, outcome, snapshot) -> GuardDecision`, `validate_dispatch(proposal, snapshot) -> GuardDecision`.

- [x] Viết table tests 7 INTENTS có dấu/không dấu, phủ định/trích dẫn, ask_human cùng abuse, want_more mơ hồ; assert human thắng, abuse tăng độc lập và không suy xu từ keyword chung. Test turn 8 thay tiền/hủy chưa claim, abuse 3 handoff; open không tăng lượt; pending/transferred/completed không action mới.
- [x] Test coins: late 1/2, mọi fault, unknown_feed, missing ledger/evidence resolver, customer-open, contact accepted/sent, web_voice/transcript, typed confirm; chỉ explicit text hợp lệ sinh `Action(kind='coins', source='a1', queue='care', needs_approval=False)` với `late_xu_for` đúng (None/0 -> 10000, giá trị sai reject). Test cancel ID/principal/order/reply-to/TTL 10 phút: tại expires_at coi hết hạn, amount 0, queue cancel_review, approval True; đổi ý vô hiệu pending.
- [x] Test `test_freshness_boundaries`: đúng feed 30/heartbeat 60/assessment 30 phút hợp lệ, vượt 1 microsecond chặn quyền tương ứng; missing/corrupt/stale, sai identity, future timestamp và evidence sau cutoff đều chặn proactive/xu; inbound vẫn có handoff. Test ETA None không bịa ngày; raw driver/PII/injection không vào public output hoặc thay facts.
- [x] Chạy `pytest -q care_truc/tests/test_policy.py care_truc/tests/test_guards.py`; expect RED.
- [x] Implement pure rules và catalog phrase ID phiên bản cố định; assessment reference hash canonical toàn bộ assessment, không trộn fields. Renderer format facts bằng code; fallback/template cũng qua validator. Summary từ state, customer quote có nhãn và không trở thành fact. Core guards luôn chạy, không phụ thuộc hooks.
- [x] Chạy lại tests, expect PASS; commit `feat(care): add deterministic care policy and validated responses`.

### Task 5: Hook phases và phrase selection có giới hạn

**Files:** Create `care_truc/hooks.py`, modify `care_truc/phrases.py`, create `care_truc/tests/test_hooks.py`, `care_truc/tests/test_phrase_selection.py`.

**Interfaces:** `RuntimeHooks.run(phase, immutable_input, *, deadline) -> HookDecision`; `build_model_context(outcome, context, history) -> bytes | None`; `select_phrase(selector, context, allowed_ids, token, clock) -> PhraseSelection` async, gọi chỉ sau durable reserve ở Task 3.

- [x] Tests hook order on_input/before_model/after_model/before_action/after_action/on_error, 100 ms tổng một phase, empty registry vẫn guard, veto không đảo. Exception/timeout: on_input blocked, model hooks fallback, before_action block, observers chỉ ghi lỗi; nested mutation bị reject hoặc không ảnh hưởng state. Registry freeze và version từ startup.
- [x] Test message 4000/4001 code points và context UTF-8 12000/12001 bytes, output 2048/2049 bytes; prune oldest tới <=4 turns, mandatory context quá lớn bỏ model mà memory còn nguyên. Output chỉ schema `{"phrase_id": "allowed-id"}`; ngày/tiền tự do, extra fields/tool call/ID lạ/invalid JSON -> fallback; callback sau 3 giây hoặc token cũ không ghi gì. Prompt không raw driver notes/PII/secrets/DB paths/ledger.
- [x] Chạy `pytest -q care_truc/tests/test_hooks.py care_truc/tests/test_phrase_selection.py`; expect RED.
- [x] Implement timeout bằng clock/deadline cancellable; không giữ DB transaction, không model repair loop; parser kiểm bytes trước decode/JSON. Sau model dù hợp lệ vẫn render bằng facts và validate. Hooks không nhận gateway/model/shell capabilities.
- [x] Chạy lại tests, expect PASS; commit `feat(care): bound hook execution and model phrase selection`.

### Task 6: CareHarness và request ownership trong process

**Files:** Create `care_truc/harness.py`, `care_truc/tests/test_turn_loop.py`.

**Interfaces:** Async `CareHarness.open_chat(order_id: str, request_id: str, ctx: TrustedRequestContext) -> TurnResult`, `open_contact(task: ContactTask, ctx) -> TurnResult`, `handle_message(session_id: str, message_id: str, text: str, ctx, reply_to: str | None = None) -> TurnResult`, `confirm_cancel(confirmation_id: str, request_id: str, ctx) -> TurnResult`, `request_handoff(session_id: str, request_id: str, ctx) -> TurnResult`. Các mutation chuyển thành typed event và đi chung `_process_event(session_id, event, ctx) -> TurnResult`; open dùng idempotency theo principal/order/request hoặc contact key.

- [x] Test trace thứ tự 10 phases spec §5; rules/human/turn8 trước model; message chỉ tăng một lượt sau commit. Same ID/payload trả response bất biến, khác payload/kind conflict; processing owner sống trả processing; request khác session đang bận trả session_busy. Có model chờ ở session A, B vẫn xong.
- [x] Test wrong principal trên cache hit vẫn bị từ chối; input fail không tạo request; context timeout 2 giây sau authorize trả limited facts/handoff mà không mở tiền. Commit lỗi không gửi, không tăng counters và không trả success. POST sinh effect chỉ `pending_delivery`, không ghi đã gửi/cấp xu.
- [x] Test orphan owner trong cùng process: finally xóa owner, retry dùng payload lưu và context mới, giữ model budget; due retry_wait theo 1/5 giây, attempt 3 thất bại -> failed_terminal ổn định. Invariant/policy exception terminal ngay, service error store không giả owner sống.
- [x] Chạy `pytest -q care_truc/tests/test_turn_loop.py`; expect RED.
- [x] Implement ingress authorize trước dedup, try-acquire session lock không queue vô hạn, owner registry theo live asyncio.Task, final commit optimistic version; callbacks kiểm token/boot. Lock bao phủ lượt nhưng DB chỉ mở ngắn; nhả finally. Chưa gọi dispatcher trực tiếp trong transaction/response path.
- [x] Chạy lại tests, expect PASS; commit `feat(care): orchestrate bounded idempotent customer turns`.

### Task 7: Dispatcher gate và race tại claim

**Files:** Create `care_truc/dispatcher.py`, `care_truc/tests/test_dispatch_races.py`.

**Interfaces:** `EffectDispatcher.drain_pending(*, limit: int = 20, start_budget_s: float = 2.0) -> DrainReport` async. Consumes proposals/claim từ Task 3; cùng session lock registry với Task 6. `CareHarness.drain_pending()` chỉ delegate nội bộ platform.

- [x] Tests dùng barriers: đổi ý/handoff commit trước claim -> blocked và 0 network; sau claim -> ghi đang gửi/chờ, không nói thu hồi. Thay session version/revision trong lúc hook chạy -> claim fail, re-evaluate; stale revision không gửi. Hai session cùng order không claim hai payload. Gateway gate chặn control đổi sau local claim.
- [x] Test missing gate/gateway/evidence resolver, hook veto hoặc business denial -> không submit; context quyền mới không cho payload cũ -> lookup/handoff, không sửa payload đã frozen. Assert gateway có thể await trong lúc session mutation mới chạy (network không giữ session lock/transaction).
- [x] Chạy `pytest -q care_truc/tests/test_dispatch_races.py`; expect RED.
- [x] Implement local guards và before_action trên snapshot, giữ session lock giai đoạn chuẩn bị/claim; transaction so version/revision và commit in_flight/attempt/budget; nhả cả lock và transaction trước network. Gate nguyên tử platform không được thay bằng bool local. Chỉ dispatch ba effect types trong spec, không generic arbitrary Action ingress.
- [x] Chạy lại tests, expect PASS; commit `feat(care): fence effect dispatch at durable claim`.

### Task 8: Retry, lookup và authoritative receipts

**Files:** Modify `care_truc/{dispatcher,effect_store,store}.py`, create `care_truc/tests/test_receipts.py`.

**Interfaces:** `EffectDispatcher.reconcile(effect_id: str) -> None` async; `MemoryStore.record_receipt` của Task 3 lưu transport/outcome riêng và dedup system event theo effect/revision.

- [x] Test remote accepted rồi timeout -> unknown/needs_reconciliation, lookup trước retry, cùng key/payload; delivered không submit lại. Accepted/awaiting_approval không succeeded; contact queue accepted không sent; cancel receipt không tuyên bố đã hủy; handoff durable ack mới transferred.
- [x] Test submission <=3, lookup <=1/effect/drain và <=3 consecutive inconclusive tổng qua restart, backoff 1/5; thiếu lookup/hết budget -> needs_reconciliation và việc cho staff, không reset từ khách/model. Business refusal/permission denial không retry; unknown không bị đổi rejected vì chờ lâu. Authoritative lookup reset consecutive inconclusive counter.
- [x] Test duplicate receipt no-op, old revision ignored, same revision different content adapter error, conflicting terminals rejected; sai key/payload/effect/source không cập nhật. Observer/log failure không rollback receipt hoặc gửi lại. Batch 20 effects/max 2 giây start, không start thêm khi shutdown.
- [x] Chạy `pytest -q care_truc/tests/test_receipts.py`; expect RED.
- [x] Implement receipt transitions có kiểm monotonic revision và terminal compatibility. Persistence precedes after_action; retries dùng exact frozen payload, permissions hiện hành và idempotent adapter. Lưu system events riêng, không sửa response POST committed.
- [x] Chạy lại tests, expect PASS; commit `feat(care): reconcile uncertain effects with bounded retries`.

### Task 9: Startup, recovery, health và shutdown

**Files:** Create `care_truc/lifecycle.py`, `care_truc/tests/test_recovery.py`; modify `care_truc/harness.py`.

**Interfaces:** `CareRuntime.start(run_id: str, adapters, hooks) -> CareRuntime` async, `recover() -> None`, `get_health() -> Health`, `shutdown() -> None`. Runtime compose store/lock/harness/dispatcher; mọi thành phần dùng cùng store và lock registry.

- [x] Tests restart tại: processing trước reserve model, sau reserve model, trước final commit, sau commit, sau claim trước network, remote nhận trước receipt. Assert counters đúng một lần; model <=1; effects in_flight phải lookup trước submit; boot cũ callback không ghi được. Replay nhảy/restart đổi monotonic origin không reset attempt hoặc bỏ backoff.
- [x] Test readiness trước recovery = not_ready; corrupt/schema/process lock/auth/context thiếu -> not_ready; model thiếu -> degraded/template chat vẫn chạy; gate/gateway thiếu chỉ block effect tương ứng; unknown effects không chặn inbound hợp lệ. Health không nội dung chat/heartbeat A3 giả.
- [x] Test shutdown reject mutation mới/ngừng start effects, chờ <=5 giây fake clock; giữ pending/in_flight, không tạo effect từ error handler; owner cleanup và lock release kể cả startup/shutdown lỗi.
- [x] Chạy `pytest -q care_truc/tests/test_recovery.py`; expect RED.
- [x] Implement startup theo spec §11, tăng boot generation sau integrity/lock; orphan resume state committed + context mới, không dùng dự kiến chưa commit. Có recovery worker tiếp tục retry_wait đến hạn trong process, không chờ restart/client mới cứu request; dùng chung ownership/processing budget. Không reset DB hoặc fake adapter fallback.
- [x] Chạy lại tests, expect PASS; commit `feat(care): recover interrupted turns and expose runtime health`.

### Task 10: In-process API, projections và bàn giao platform

**Files:** Create `care_truc/api.py`, `care_truc/tests/test_api.py`; modify `care_truc/README.md`.

**Interfaces:** `CareApi.handle(operation: str, payload: Mapping[str, object], ctx: TrustedRequestContext) -> ApiResponse` async. `CareHarness.get_messages(session_id, ctx) -> CustomerHistory`, `get_trace(session_id, ctx) -> StaffTrace` async; API staff handoff projection dùng `get_handoffs(ctx) -> tuple[HandoffSummary, ...]`. Mọi read authorize từ platform trước query/projection.

- [x] Tests mapped chat open/messages, cancel prepare (typed want_cancel đi chung event loop), confirm, handoff, staff decisions/handoffs; reject forged fields/unknown operations. Cross-principal/order và staff-less GET/retry không lộ nội dung; customer projection không trace/evidence nội bộ/PII. Confirm/handoff ID trùng message conflict, không bypass turn8; request human khi handoff_pending dùng cùng handoff key.
- [x] Test mapping 400 schema, 401 auth, 403 quyền, 404 không thấy tài nguyên, 409 request/state conflict, 503 required adapter/service error; processing/session_busy là mã cấu trúc để retry, không cache response cuối. Domain refusal là response có decision code. Health/drain/recover không được public mutation dispatcher nhận từ operation khách.
- [x] Chạy `pytest -q care_truc/tests/test_api.py`; expect RED.
- [x] Implement strict schemas theo operation, allowlists cho projections và trace; trace có references/phase/versions/codes/source/elapsed/effects, không chain-of-thought/raw prompts/notes/secrets. Trace/evidence bắt buộc nằm trong transaction; log ngoài thất bại chỉ degrade health. README ghi protocol checklist cho Huy: auth, ownership, cutoff, assessment, guard/feed policy, gate, value, evidence resolver, idempotent receipts/revisions, handoff sink và cancellation capabilities. Liệt kê route đề xuất trong spec nghiệp vụ, đánh dấu chưa mount; không thêm server/voice SDK.
- [x] Chạy lại tests, expect PASS; commit `feat(care): expose authenticated in-process care API`.

### Task 11: Acceptance xuyên suốt và bằng chứng bàn giao

**Files:** Create `care_truc/tests/test_harness_acceptance.py`; modify `care_truc/README.md` với kết quả thực tế sau thực thi.

**Interfaces:** Dùng public CareRuntime/CareApi và scripted platform ports; không gọi thẳng policy/store để giả một luồng đã chạy.

- [x] Viết test scenario public API: proactive contact accepted chưa đủ D4 -> sent receipt -> ask why -> explicit text coins -> immutable local pending response -> platform receipt succeeded -> GET system event; restart giữa các mốc vẫn một key/order. Nhánh riêng cancel/confirm/đổi ý và handoff queue lỗi rồi durable ack; nhánh model injection/timeout với guard stale vẫn inbound handoff được.
- [x] Chạy `pytest -q care_truc/tests/test_harness_acceptance.py`; xác nhận test bắt được thiếu wiring (RED nếu còn); sửa composition trong phạm vi care_truc rồi GREEN, không yếu acceptance của Huy.
- [x] Chạy `python -c "import contracts"`, `pytest -q care_truc/tests`, `pytest -q`, `git diff --check`, `python scripts/guardrails.py --all --tests`; yêu cầu exit 0. Khi môi trường thiếu dependency báo đúng blocker, không sửa requirements thuộc Huy. Xem `git status --short` và `git diff --stat`, bảo đảm chỉ files care_truc chủ đích được stage và không DB/secrets/data.
- [x] Ghi README: commands thực sự đã chạy, adapters nào fake, coverage theo bảng bên dưới, chưa ghép HTTP/provider/A3/A2/executor thật; không công bố integration production hoặc exactly-once bên ngoài. Không tạo launch command chưa tồn tại.
- [x] Commit `test(care): verify harness recovery and delivery invariants`; fetch/merge updates theo quy trình, rerun checks nếu thay đổi rồi push feature branch. Handoff Huy review adapter contracts trước nối network thật.

## Coverage theo spec

| Spec | Tasks chịu trách nhiệm |
| --- | --- |
| §§1–3 scope, components, ownership | 1, 10, 11 |
| §4 APIs, trusted envelope, clocks, event counts | 1, 4, 6, 10 |
| §5 fixed loop/atomic final response | 2, 5, 6 |
| §6 input/model/time/batch budgets | 1, 3, 5, 7–9 |
| §7 memory, evidence, schema, prompt truncation | 2–5 |
| §8 hooks/order/errors | 5, 7, 8 |
| §9 input/context/policy/output/dispatch/receipt guards | 4–8, 10 |
| §10 keys, revisions, claim race, reconciliation | 3, 7, 8 |
| §11 process/session ownership, live resume/restart/shutdown | 2, 3, 6, 9 |
| §12 trace/health/test adapters | 1, 6, 9–11 |
| §13 acceptance groups | Test modules Tasks 2–11; end-to-end fixtures Task 11 |
| §§14–15 platform approvals/handoff | 10, 11 |

## Tự rà soát plan

- Mọi nhóm nghiệm thu có task và test đích; năm Review Focus có test được giao cụ thể.
- Store là writer duy nhất; effect_store là SQL helper nội bộ, không writer độc lập. Các APIs cùng request namespace/session lock; dispatcher không giữ khóa qua network.
- Các chữ ký trên là quyết định thiết kế cho code chưa tồn tại; wire contracts dùng nguyên types chung. Chi tiết SQL/helper records phải giữ invariants, không phát minh quyền platform.
- Model provider, HTTP mount, voice transport và production retention nằm ngoài plan này; thiếu adapters phải hiện readiness/blocking đúng, không mặc định fixtures.
