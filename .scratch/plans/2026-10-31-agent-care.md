# Agent Care Implementation Plan

> **Trạng thái thực thi:** Đã triển khai Tasks 1–11 trên `truc/care-business`; review toàn nhánh đang tiến hành. Theo yêu cầu bổ sung của người dùng, đã merge harness từ main và dùng duy nhất `CareRuntime`/`CareHarness` async. Các chữ ký/file store, service, ports, dispatcher và API đồng bộ bên dưới là thiết kế ban đầu, được thay bằng interfaces hiện hành trong [README A1](../../care_truc/README.md). Các tiêu chí nghiệp vụ và tests vẫn áp dụng. [VERIFICATION](../../care_truc/VERIFICATION.md) ghi lệnh kiểm chứng, migration và giới hạn tích hợp; adapter demo không phải demo thực thi thật.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. Chỉ triển khai sau khi người dùng review spec/plan và chọn cách thực thi.

**Goal:** Xây lõi A1 chat tiếng Việt, lưu phiên bền, tạo yêu cầu xu/hủy và bàn giao có bằng chứng, kèm API adapter in-process kiểm được bằng tests.

**Architecture:** Rules và state machine thuần Python dùng shared contracts; SQLite riêng lưu mutation, response bất biến và pending deliveries trong cùng transaction. Sau commit, dispatcher gọi các cổng platform idempotent và ghi receipt/system event riêng. HTTP/auth, assessment, guard và executor thật do Huy ghép; voice để giai đoạn sau.

**Tech Stack:** Python 3.11+, dataclasses, typing.Protocol, sqlite3, pytest; không thêm dependency.

**Spec:** [2026-10-31-agent-care.md](../specs/2026-10-31-agent-care.md). Đọc cả spec và plan trước khi triển khai.

## Global Constraints

- Phạm vi sở hữu: `care_truc/`. Nhánh dự kiến trong spec: `truc/agent-care`; checkout lúc lập plan ở `truc/care-business`. Khi thực thi xác nhận nhánh làm việc theo trạng thái thực tế, không reset hoặc xóa nhánh hiện có.
- Bản spec đang chờ duyệt; lập plan không đồng nghĩa phê duyệt các lựa chọn kỹ thuật. Các lựa chọn cần review: chat trước voice sau, phrase selector có kiểm soát, API chờ Huy mount, SQLite riêng, assessment tối đa 30 phút, POST bất biến/GET receipts, xác nhận hủy 10 phút.
- Không sửa `contracts/`, dependencies, `platform_huy/`, `acceptance_truc/` hoặc tests người khác. Test A1 mới trong `care_truc/tests/`. Test chéo A2 là công việc riêng.
- Dùng trực tiếp `contracts.types` và `contracts.params`; không copy enums. Python datetime có timezone; wire UTC ISO 8601; ngày cam kết theo `Asia/Ho_Chi_Minh`.
- Không đọc release DB từ A1, không sinh world data; thời gian nghiệp vụ và dữ liệu as-of do platform cấp. State A1 tại `runs/<run_id>/care.sqlite`, không thêm bảng vào shared runtime DB.
- Assessment đúng 30 phút hợp lệ; hơn 30 phút không mở contact chủ động hoặc xét xu. Feed stale khi timestamp nguồn quá 30 phút; heartbeat A3 quá 60 phút chặn proactive. Không dùng thời gian replay thay timestamp nguồn.
- `max_turns=8`; lượt 8 bàn giao; abuse lượt 3 bàn giao; yêu cầu gặp người có ưu tiên cao nhất. Retry không tăng counters. Sau handoff_pending/transferred/completed không sinh action tự động mới.
- Xu chỉ từ text yêu cầu rõ ràng trong chat A1 mở đã gửi contact thành công; `late_days >= 2`, fault carrier/platform, facts đáng tin, chưa grant/chưa pending. Voice không cấp xu. Mọi action tiền qua gateway tới executor platform.
- Coins: source `a1`, queue `care`, needs_approval=False; cancel_request: amount 0, source `a1`, queue `cancel_review`, needs_approval=True, confirmation_id bắt buộc. Executor vẫn kiểm quyền/controls và có thể yêu cầu review.
- POST có side effect chỉ xác nhận local `pending_delivery`; response retry bất biến. Chỉ GET/system event phản ánh receipt mới; không báo gửi/cấp thành công khi chưa có xác nhận bền có thẩm quyền.
- Không cài hooks. Khi thực thi, fetch team remote, merge cập nhật nhánh nếu có và main trước công việc/push; giữ local changes. Commit/push từng unit đã kiểm chứng, không force push hay merge main nếu chưa được yêu cầu.

## Review Focus

1. Hai process cùng sửa một phiên hoặc cùng xin xu cho một order: transaction/unique constraints phải giữ một mutation, một pending request; test Task 3 và 7.
2. Datetime naive, offset khác UTC, cutoff đi lùi hoặc ở tương lai: normalize ở boundary, từ chối input không xác định, không vô tình coi facts tương lai là fresh; test Task 1 và 2.
3. Unicode, dấu câu, câu phủ định/trích dẫn chứa nhiều intent: không cấp quyền hủy/tiền từ keyword đơn lẻ; test Task 4.
4. Receipt đến trễ, lặp hoặc sai action/key sau timeout: không làm lùi succeeded, không cập nhật nhầm phiên, không nhân system event; test Task 9.
5. Client chèn trường server hoặc đoán ID của người khác: từ chối payload và không lộ existence/trace/PII; test Task 10.

## File structure và interfaces dùng chung

Hiện `care_truc/` chỉ có README; các file Python dưới đây là file mới. Shared contracts đã đọc: `OrderAssessment`, `ContactTask`, `Action`, `Intent`, `Channel`, `Evidence`; `Action` có một `evidence_ref: str`, không có contact_id/evidence_refs. `late_xu_for` đã từ chối bool, sai kiểu và số âm.

| File | Trách nhiệm |
| --- | --- |
| `care_truc/__init__.py` | Export service/API public sau khi có implementation |
| `care_truc/models.py` | Dataclasses A1, state, commands/results và runtime validation |
| `care_truc/ports.py` | Protocols với platform, store, phrase selector |
| `care_truc/context.py` | Validate context as-of, assessment và guard |
| `care_truc/schema.sql`, `care_truc/store.py` | SQLite A1, atomic mutation, idempotency, outbox, receipts |
| `care_truc/rules.py` | 7 intent, abuse, explicit coin request, phủ định/trích dẫn |
| `care_truc/rendering.py` | Templates, public evidence projection, phrase validation |
| `care_truc/handoff.py` | Summary render bằng code, một handoff mỗi phiên |
| `care_truc/coins.py`, `care_truc/cancellation.py` | Pure eligibility và pending confirmation/action builders |
| `care_truc/service.py` | Điều phối domain transitions, dùng transaction store |
| `care_truc/dispatch.py` | Gửi sau commit, reconcile receipt, recovery |
| `care_truc/api.py` | JSON in-process handlers, serialization và status mapping |
| `care_truc/tests/conftest.py`, `care_truc/tests/fakes.py` | Fixtures thuật toán và memory adapters chỉ dùng test |
| `care_truc/demo.py`, `care_truc/README.md` | Demo adapter có nhãn và hướng dẫn ghép |

Các type sau thuộc `models.py`, không thay shared contracts:

- `Principal(customer_id: str, is_staff: bool)`; `TrustedContext(principal: Principal, run_id: str, cutoff: datetime)`, chỉ server tạo.
- `AssessmentRef(order_id: str, assessed_at: datetime)`; `CareContext(assessment: OrderAssessment | None, contact: ContactTask | None, items_value_vnd: int | None, guard: GuardSnapshot | None, grant_state: Literal['none','pending','granted','unknown'])`. Reader phải validate ownership bằng trusted principal, trả đúng một assessment hoàn tất as-of.
- `GuardSnapshot(agent_id: str, heartbeat_at: datetime | None, required_feeds: tuple[str,...], feeds: tuple[FeedSnapshot,...], controls: tuple[str,...])`; `FeedSnapshot(name: str, status: str, source_timestamp: datetime | None)`. `agent_id='a3'`, policy feeds và controls được platform adapter map từ server; code chặn khi snapshot thiếu/không nhận diện policy.
- `Session`: id, principal_id, run_id, order_id, channel, origin (`a1`/`customer`), contact, contact_delivery_status, state, version, turn_count, abusive_turn_count, pending_cancel_id. State đúng năm giá trị trong spec.
- `MessageCommand(request_id: str, text: str, channel: Channel, reply_to: str | None)`; channel do server route/session xác định, không lấy từ client.
- `IntentSignals(intent: Intent, abusive: bool, explicit_coins: bool, cancel_retracted: bool)`.
- `TurnResponse(message_id: str, text: str, intent: Intent, assessment_ref: AssessmentRef | None, evidence_refs: tuple[str,...], decision_codes: tuple[str,...], action_refs: tuple[str,...], response_source: Literal['template','phrase_selector'], delivery_status: str | None)`.
- `PendingCancel`: id ngẫu nhiên, principal_id, session_id, order_id, contact_id (có thể None inbound), version, prompt_message_id, expires_at, status.
- `PendingDelivery`: id, session_id, kind (`contact`/`action`/`handoff`), key, payload, status, lease_until; `Receipt`: delivery_key, external_id, status (`accepted`/`pending`/`unknown`/`blocked`/`failed`/`succeeded`), revision, evidence_ref. Gateway adapter phải ánh xạ receipt có thứ tự revision; timeout không tạo failed giả.
- `HandoffSummary`: id, session_id, reason, customer_need, facts, evidence_refs, action_receipts, cancellation_state, staff_decisions_needed.
- `GateDecision(allowed: bool, codes: tuple[str,...])`, `Eligibility(allowed: bool, codes: tuple[str,...], amount_vnd: int | None)`, `DomainError(code: str, http_status: int)`; customer projection không chứa trace.

`ports.py` dùng Protocol, không import framework/provider:

```python
class ContextReader(Protocol):
    def read(self, trusted: TrustedContext, order_id: str,
             assessment_ref: AssessmentRef | None = None) -> CareContext: ...

class ContactGateway(Protocol):
    def dispatch_checked(self, trusted: TrustedContext,
                         delivery: PendingDelivery) -> Receipt: ...
    def lookup(self, key: str) -> Receipt | None: ...

class ActionGateway(Protocol):
    def submit(self, trusted: TrustedContext, action: Action) -> Receipt: ...
    def lookup(self, key: str) -> Receipt | None: ...

class HandoffSink(Protocol):
    def submit(self, trusted: TrustedContext, summary: HandoffSummary,
               key: str) -> Receipt: ...
    def lookup(self, key: str) -> Receipt | None: ...

class PhraseSelector(Protocol):
    def select(self, template_id: str, allowed_phrase_ids: tuple[str,...]) -> object: ...
```

`dispatch_checked` phải kiểm controls/guard mới nhất và dispatch như một quyết định platform; thiếu capability này trả blocked. Không fallback sang gửi trực tiếp. `ActionGateway` là đường duy nhất tới `platform_huy.execute_action`, chịu trách nhiệm durable receipt và uniqueness order. Những chữ ký này là đề xuất A1 cần Huy map adapter, không tuyên bố platform đã có chúng.

## Task 1: Chốt domain types và ports có validation

**Files:** Create `care_truc/__init__.py`, `models.py`, `ports.py`, `tests/conftest.py`, `tests/fakes.py`, `tests/test_models.py`.

**Interfaces:** Produces các type/protocol ở trên; `normalize_utc(value: datetime) -> datetime` và `validate_context_time(trusted: TrustedContext) -> None` trong models. Principal phải tồn tại, cutoff aware; run_id chỉ nhận tên segment an toàn, không nhận path traversal.

- [x] Viết `test_boundary_types`: assert datetime naive gây DomainError 400; offset +07 được normalize UTC cùng instant; bool/âm/sai kiểu items_value bị từ chối; run_id `../other` bị từ chối. Kiểm Action serialization giữ đúng fields contract.
- [x] Chạy `pytest care_truc/tests/test_models.py -q`; xác nhận fail vì module/types chưa tồn tại.
- [x] Tạo dataclasses frozen/slots cho values, enums bằng Literal cho A1 state, validate dữ liệu ngoài boundary. Memory adapters chỉ đặt trong tests; `__init__` không export fake executor.
- [x] Chạy lại test, expected PASS; commit `feat(care): define domain models and platform ports` với các file Task 1.

## Task 2: Context as-of, freshness và proactive gate

**Files:** Create `care_truc/context.py`, `care_truc/tests/test_context.py`.

**Interfaces:** Consumes Task 1; produces `validate_assessment(ctx: CareContext, trusted: TrustedContext, order_id: str, initial_ref: AssessmentRef | None) -> None`, `assessment_is_current(assessment: OrderAssessment, cutoff: datetime) -> bool`, `check_proactive(guard: GuardSnapshot | None, cutoff: datetime) -> GateDecision`.

- [x] Viết tests với cutoff cố định: tuổi assessment 30 phút true, 30 phút +1 giây false, assessed_at tương lai/sai order/contact mismatch gây structured error. Timestamp evidence > cutoff bị từ chối; không merge fields từ hai assessments. Reader nhận initial_ref chính xác lúc mở contact; các lượt sau dùng snapshot mới hoàn tất và lưu ref.
- [x] Parameterize gate: feed đúng 30 phút cho qua, +1 giây chặn; heartbeat đúng 60 phút cho qua, +1 giây chặn; thiếu guard/feed/heartbeat, wrong identity, timestamps tương lai, stale/corrupt/missing hoặc blocking controls đều chặn. Test cutoff đi lùi không hợp thức hóa future snapshot.
- [x] Chạy `pytest care_truc/tests/test_context.py -q`, expected FAIL; triển khai signatures trên bằng timestamp nguồn, không gọi datetime.now để quyết nghiệp vụ.
- [x] Chạy lại expected PASS; commit `feat(care): validate as-of context and contact gates`.

## Task 3: SQLite transaction, idempotency và durable outbox

**Files:** Create `care_truc/schema.sql`, `care_truc/store.py`, `care_truc/tests/test_store.py`.

**Interfaces:** `SqliteSessionStore(path: Path)`; `mutate(principal_id: str, session_id: str, request_id: str, payload_hash: str, transition: Callable[[Session], Mutation]) -> TurnResponse`; `Mutation` chứa session mới, message, frozen response JSON, evidence và deliveries. Store cung cấp `create_session(session: Session, contact_key: str | None) -> Session`, `history(principal_id: str, session_id: str) -> History`, `claim_deliveries(cutoff: datetime, limit: int) -> tuple[PendingDelivery,...]`, `record_receipt(receipt: Receipt) -> None`. `History` chứa public messages/events/delivery state; staff trace đọc riêng Task 10.

- [x] Viết tests: retry cùng principal/session/request/payload trả response byte-equivalent và counters không đổi; khác payload 409; rollback không để nửa message/response/outbox. Close/reopen giữ state.
- [x] Test bằng hai connection cùng SQLite tạm: cùng message chỉ một mutation; UNIQUE contact key; một open handoff/session; coin key unique run/order, kể cả hai phiên; lease tránh hai dispatcher xử lý cùng lúc. Dùng file tạm cho restart/concurrency, in-memory cho tests cô lập không cần reopen.
- [x] Chạy `pytest care_truc/tests/test_store.py -q`, expected FAIL. Tạo bảng A1 sessions/messages/requests/evidence/cancellations/deliveries/receipts/system_events. `BEGIN IMMEDIATE` khóa writer; rollback đầy đủ, bounded busy handling thành conflict/retryable error. Hash canonical payload gồm text/reply-to và operation; unique request scope principal/session; kiểm ownership trước trả cache.
- [x] Lưu session, evidence bền, message, pending intent, response cùng transaction; callback transition chỉ pure code, không gọi network/LLM. Không giữ transaction khi chờ adapter. System event UNIQUE delivery key/revision/status, receipt không được lùi terminal state.
- [x] Chạy lại expected PASS; commit `feat(care): persist atomic turns and pending deliveries`.

## Task 4: Rules, templates và phrase selector an toàn

**Files:** Create `care_truc/rules.py`, `rendering.py`, `tests/test_rules.py`, `tests/test_rendering.py`.

**Interfaces:** `classify(text: str) -> IntentSignals`; `render(template_id: str, ctx: CareContext, signals: IntentSignals, selection: object | None = None) -> RenderedReply`; RenderedReply gồm text/public evidence/decision codes/source. `select_phrases(selector: PhraseSelector | None, template_id: str) -> object | None` chạy ngoài transaction, lỗi thành fallback code.

- [x] Viết parameterized tests cho đủ INTENTS; câu có dấu/không dấu, Unicode normalize, `tôi không muốn hủy`, `tài xế bảo tôi hủy`, hỏi policy xu, xin hỗ trợ mơ hồ, câu gặp người kèm chửi. Assert ask_human thắng, abusive vẫn true, chỉ yêu cầu xu hiện tại rõ ràng mới explicit_coins true.
- [x] Test unknown reason → `chưa đủ thông tin để xác nhận nguyên nhân`; ETA None → chưa xác định, guaranteed_date không làm ETA. Inbound facts cũ có thời điểm cập nhật và không gọi ETA cũ là dự báo hiện tại. Opening có tình trạng/ngày cam kết/ETA nếu có/xin lỗi, không gợi xin xu.
- [x] Test mọi output selector có amount/date/promise tự do, ID lạ, slot lạ, sai schema, timeout/provider error fallback template; legacy text chỉ nhận exact approved variant. Assert response không lộ driver name/phone/raw note; driver/customer injection không đổi facts/actions.
- [x] Chạy `pytest care_truc/tests/test_rules.py care_truc/tests/test_rendering.py -q`, expected FAIL. Implement mapping reason→approved template+structured evidence fact codes. Không có reason đã thống nhất thì neutral fallback; LLM chỉ chọn phrase IDs, renderer gắn facts cuối; không gửi raw text/PII sang selector.
- [x] Chạy lại expected PASS; commit `feat(care): add deterministic intent rules and safe replies`.

## Task 5: State machine chat và contact chủ động

**Files:** Create `care_truc/service.py`, `tests/test_service.py`; Modify `models.py`, `ports.py` chỉ để hoàn thiện types đã định nghĩa.

**Interfaces:** `CareService(store, reader, contact_gateway=None, action_gateway=None, handoff_sink=None, phrase_selector=None)`; `open_chat(trusted: TrustedContext, order_id: str, request_id: str) -> Session`; `prepare_contact(trusted: TrustedContext, contact: ContactTask) -> Session`; `message(trusted: TrustedContext, session_id: str, command: MessageCommand) -> TurnResponse`.

- [x] Tests: client open luôn origin customer; chỉ internal prepare_contact được origin a1. Proactive stale/invalid context chặn; opening không tăng turn_count; contact chuẩn bị chỉ pending, không marked sent. Duplicate contact key trả phiên cũ, key trùng payload khác 409.
- [x] Tests: mỗi accepted message tăng turn một lần; retry trước/sau terminal trả nguyên response; turn 8/abuse 3/human request chuyển handoff_pending, không mở quy trình coins/cancel mới; human cùng cancel thắng. Phiên terminal nhận message mới trả state conflict và không side effect. Missing context không sinh action nhưng principal hợp lệ vẫn được yêu cầu gặp người.
- [x] Chạy `pytest care_truc/tests/test_service.py -q`, expected FAIL. Điều phối reader/selector trước transaction; mutation kiểm version/context ref để không ghi kết quả dựa trên phiên đã đổi. Version conflict trả 409/retry, không tự đếm lượt lần hai. Pending cancellation chỉ thay đổi qua Task 8; handoff payload hoàn thiện Task 6.
- [x] Chạy lại expected PASS; commit `feat(care): orchestrate durable chat transitions`.

## Task 6: Handoff có ngữ cảnh và trạng thái gửi thật

**Files:** Create `care_truc/handoff.py`, `tests/test_handoff.py`; Modify `service.py`.

**Interfaces:** `build_handoff(session: Session, history: History, reason: str) -> HandoffSummary`; `CareService.handoff(trusted: TrustedContext, session_id: str, request_id: str, reason: str) -> TurnResponse`.

- [x] Tests assert summary có order, nhu cầu khách được gắn nhãn, assessment/evidence, known receipt, cancellation validity, việc nhân viên quyết định. Explicit human/abuse 3/turn 8/thiếu facts để xử lý nhu cầu đều enqueue một handoff; thiếu ETA câu hỏi thông thường không bắt buộc handoff.
- [x] Tests sink lỗi giữ handoff_pending, không nói đã chuyển; retry một bản; chưa accepted không transferred. Handoff vô hiệu pending cancel, không hứa thời gian phản hồi. Chỉ projection staff có nội dung nội bộ.
- [x] Chạy `pytest care_truc/tests/test_handoff.py -q`, expected FAIL; triển khai renderer bằng code, stable key `handoff:{run_id}:{session_id}` và outbox, chưa gọi sink trong mutation.
- [x] Chạy lại expected PASS; commit `feat(care): persist contextual human handoffs`.

## Task 7: D4 eligibility và yêu cầu coins

**Files:** Create `care_truc/coins.py`, `tests/test_coins.py`; Modify `service.py`.

**Interfaces:** `evaluate_coins(session: Session, command: MessageCommand, signals: IntentSignals, ctx: CareContext, trusted: TrustedContext) -> Eligibility`; `build_coin_action(session: Session, eligibility: Eligibility, evidence_ref: str, cutoff: datetime) -> Action`.

- [x] Parameterize từng điều kiện D4: origin/contact sent/channel/explicit request/late_days/fault/status/freshness/guard/trusted facts/grant state. Assert chỉ chat A1 đã dispatch thành công, current text explicit, late>=2, carrier/platform, grant none và facts tốt cho allowed. Customer chat, web_voice/transcript, policy question, vague want_more, unknown_feed/fault, pending/unknown ledger đều không enqueue.
- [x] Test `None/0 -> 10000`, 300000 → 15000, 1 → floor 10000, 100000000 → cap 1000000; bool/string/float/âm reject; assert dùng contract `late_xu_for`, không tính lại.
- [x] Tests liên phiên/message ID mới cùng run/order chỉ một pending action; cross-run local key khác nhưng platform vẫn UNIQUE order grant. Evidence_ref resolve bền tới contact/current customer message/assessment/eligibility. Thiếu gateway không tạo receipt giả hoặc ghi ledger.
- [x] Chạy `pytest care_truc/tests/test_coins.py -q`, expected FAIL; implement key `coins:{run_id}:{order_id}`, Action fields theo Global Constraints, store reservation cùng mutation. Local response chỉ ghi nhận pending; platform sẽ recheck eligibility/amount/permission/order uniqueness.
- [x] Chạy lại expected PASS; commit `feat(care): enforce text-only compensation eligibility`.

## Task 8: Hủy với xác nhận lần hai có ràng buộc

**Files:** Create `care_truc/cancellation.py`, `tests/test_cancellation.py`; Modify `service.py`.

**Interfaces:** `new_pending_cancel(session: Session, prompt_message_id: str, cutoff: datetime) -> PendingCancel`; `validate_confirmation(pending: PendingCancel, session: Session, trusted: TrustedContext, reply_to: str | None) -> None`; `CareService.prepare_cancel(trusted, session_id: str, request_id: str) -> TurnResponse`; `CareService.confirm_cancel(trusted, pending_id: str, request_id: str, reply_to: str | None, confirmed: bool) -> TurnResponse`.

- [x] Tests request lần đầu chỉ tạo awaiting_cancel_confirmation, không Action; id không đoán được; expires_at=cutoff+10 phút. Confirm chỉ khi cutoff < expires_at; đúng expires_at đã hết hạn. Sai principal/order/contact/version, old pending/reply-to sai, confirmed false, hoặc `đồng ý` không gắn prompt đều không enqueue.
- [x] Tests pending mới thay cũ; đổi ý/handoff invalidate; expired yêu cầu lại không tự gia hạn. Confirm route retry cùng payload trả đúng response; request ID khác confirm đã dùng trả action cũ, không thêm action; khác payload cùng ID 409.
- [x] Chạy `pytest care_truc/tests/test_cancellation.py -q`, expected FAIL; tạo token bằng secrets, stable key theo pending_id, evidence bền, Action cancel fields theo Global Constraints. Confirm thành công chuyển lại active và lưu consumed pending; không báo hủy/hoàn tiền thành công. Confirm là một accepted customer turn và cũng chịu human/turn-limit terminal gates, không là lối né lượt 8.
- [x] Chạy lại expected PASS; commit `feat(care): require scoped second cancellation confirmation`.

## Task 9: Dispatch, receipt và restart recovery

**Files:** Create `care_truc/dispatch.py`, `tests/test_dispatch.py`, `tests/test_recovery.py`; Modify `store.py`, `service.py` khi nối dispatcher.

**Interfaces:** `Dispatcher(store, contact_gateway=None, action_gateway=None, handoff_sink=None)`; `drain(trusted: TrustedContext, limit: int = 20) -> int`; `reconcile(trusted: TrustedContext, delivery: PendingDelivery) -> Receipt | None`. Dispatcher lấy snapshot trusted mới từ platform mỗi lần drain, không dùng snapshot đã chuẩn bị làm phép gửi.

- [x] Tests controls đổi giữa prepare và dispatch khiến contact blocked; thiếu dispatch_checked blocked, không gọi send trực tiếp; contact chỉ sent sau accepted bền. Action accepted chưa được nói đã cấp; succeeded có thẩm quyền mới thêm event đã cấp. Handoff accepted mới transferred.
- [x] Crash tests tại ba điểm: message/outbox đã commit trước send; platform đã nhận trước local receipt; receipt đã commit trước client GET. Reopen store, lookup trước retry gửi cùng key; timeout giữ unknown/pending, không tạo action/key mới. Lease hết hạn phục hồi worker chết, không giữ SQLite transaction qua network.
- [x] Tests duplicate receipt/restart chỉ một event; revision cũ không làm lùi succeeded; key sai không cập nhật delivery; pending→accepted→succeeded hợp lệ. Retry POST byte-equivalent sau dispatch trong khi GET có event/status mới. Terminal session không xóa bỏ pending delivery hợp lệ đã commit trước đó; dispatcher không sinh quyết định action mới.
- [x] Chạy `pytest care_truc/tests/test_dispatch.py care_truc/tests/test_recovery.py -q`, expected FAIL. Implement claim→commit→lookup/submit→record receipt. Platform idempotency và UNIQUE order là điều kiện bắt buộc; SQLite không chứng minh exactly-once bên ngoài.
- [x] Chạy lại expected PASS; commit `feat(care): reconcile durable deliveries after restart`.

## Task 10: In-process API, auth boundary và public projection

**Files:** Create `care_truc/api.py`, `tests/test_api.py`; Modify `__init__.py` exports.

**Interfaces:** `CareApi(service: CareService, store: SqliteSessionStore)`; `handle(method: str, path: str, payload: dict[str, object], trusted: TrustedContext | None) -> ApiResponse`; `ApiResponse(status: int, body: dict[str, object])`. Không dựng HTTP server; Huy dựng trusted principal và kiểm ownership qua reader trước handler domain.

- [x] Tests tất cả routes spec: POST chats; GET/POST chat messages; POST order cancel-requests (body session_id bắt buộc để chọn đúng phiên); POST cancel-request confirm; POST chat handoff; staff GET handoffs/decisions. Decisions chỉ là đề xuất mount cần Huy duyệt, in-process handler vẫn có test.
- [x] Tests 400 malformed/unknown fields; 401 thiếu principal; 403 nonstaff gọi staff endpoint; 404 resource không thuộc quyền xem (kể cả đoán session/cancel ID); 409 request/state conflict; 503 adapter bắt buộc chưa sẵn sàng. Domain refusal trả response nghiệp vụ 200 với decision code, không giả system failure.
- [x] Tests client gửi source/proactive/customer_id/cutoff/allowed/channel server bị reject; staff trace không lộ trong public history/errors; missing assessment structured error, không on_track giả. GET ordering có stable message/event IDs, không lộ raw driver notes.
- [x] Chạy `pytest care_truc/tests/test_api.py -q`, expected FAIL; implement strict payload allowlist và serialization UTC. TrustedContext chỉ nhận từ tham số server, không parse từ JSON. Open inbound có thể lưu phiên thiếu logistics để nhận human request; không tạo action trên context thiếu.
- [x] Chạy lại expected PASS; commit `feat(care): expose authenticated in-process chat handlers`.

## Task 11: Demo có nhãn, regression và bàn giao Huy

**Files:** Create `care_truc/demo.py`, `care_truc/tests/test_flow.py`; Modify `care_truc/README.md`. Không sửa docs của Huy.

**Interfaces:** `python -m care_truc.demo` chạy scenario adapter test có nhãn rõ `adapter demo`; không dựng fake executor production và không tuyên bố HTTP/integrated demo.

- [x] Viết flow test với memory adapters được inject rõ ràng: proactive→ask_why→explicit coins→GET receipts; nhánh riêng hủy confirm; nhánh human handoff; selector độc hại fallback; guard xấu blocked. Assert mọi action có evidence resolve được, replay POST giữ nguyên, staff nhìn đủ summary, khách không thấy PII.
- [x] Chạy `pytest care_truc/tests/test_flow.py -q`, expected FAIL trước khi nối demo; triển khai demo dùng fixtures thuật toán có nhãn, tuyệt đối không ghi vào release DB hoặc trình bày fixture như dữ liệu thế giới. README ghi signatures, cách inject adapters thật, polling GET và recovery.
- [x] Chạy `python -c "import contracts"`, `pytest care_truc/tests -q`, `pytest -q`, `git diff --check`, `python scripts/guardrails.py --all --tests`. Expected exit 0, tests không sửa/skip acceptance của Huy để vượt gate. Chạy `python -m care_truc.demo` và đối chiếu assertions với output thật.
- [x] README ghi rõ phần Huy cần cung cấp: ownership/principal/cutoff, assessment hoàn tất và giá hàng as-of, policy required feeds, atomic latest-control dispatch, gateway có lookup/receipt/order uniqueness, handoff sink, mount/auth HTTP, duyệt route decisions. Voice/provider/session negotiation chưa ghép; không bật voice endpoint thành công giả.
- [x] Commit `feat(care): document and verify chat adapter flows`; trước push fetch/merge cập nhật team rồi chạy lại checks nếu có thay đổi. Push nhánh feature hiện hành theo AGENTS, không push main. Nếu `.scratch/` ignored thì để spec/plan local, không force-add.

## Coverage và completion gates

| Spec | Task chịu trách nhiệm |
| --- | --- |
| Context, identity, as-of, assessment tuổi, ETA | 1, 2, 4, 5 |
| Session, intent, counters, terminal priority | 3, 4, 5 |
| Public evidence, controlled renderer, injection | 4, 10 |
| Proactive prepare/dispatch và D3 boundaries | 2, 5, 9 |
| D4, quote, uniqueness/evidence/receipt | 3, 7, 9 |
| Hủy lần hai, expiry, invalidation | 5, 8 |
| Handoff summary/delivery | 6, 9 |
| SQLite recovery, immutable POST, current GET | 3, 9, 10 |
| API, ownership, staff, errors | 1, 10 |
| Adapter demo, integration limits, tests | 11 |

Lõi hoàn thành khi Task 1–11 có bằng chứng tests mới chạy và mọi pending/unknown đều được phản ánh trung thực. Tích hợp thật chỉ hoàn thành sau Huy cung cấp adapters và kiểm được một đơn release thật ở cutoff hợp lệ; không có đơn đủ D4 thì demo từ chối đúng điều kiện. Voice là kế hoạch riêng sau khi chọn provider, mọi transcript giữ `web_voice`; không chuyển thành D4 text request bằng cách đổi nhãn.

## Self-review khi lập plan

Đã đối chiếu các mục spec với bảng coverage, kiểm chữ ký/types giữa tasks và gắn năm Review Focus vào tests tương ứng. Plan không thay D1–D5 hoặc shared contracts; không dùng schema platform cho state A1. CodeGraph chưa initialized tại checkout lúc lập plan, đã hỏi người dùng riêng; cấu trúc scaffold và contracts được đọc trực tiếp, không giả định agent/API có sẵn. Chưa chạy implementation tests vì công việc hiện tại chỉ tạo kế hoạch.
