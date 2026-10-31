# Thiết kế platform Huy, bản đầu — 31/10/2026

> **Reviewed for implementation planning; implementation not started.** [Independent review — final approval](2026-10-31-huy-demo-spec-review.md#re-review-of-revised-spec--2026-10-31). Huy đã chọn Next tick thủ công +30 phút, chat phản hồi ngay (wall time chỉ audit), human verification có bằng chứng/audit cho positive demo. Coins và voucher10.000 VND là issuance SQLite nội bộ, độc lập once/kind/order, cùng eligibility; redemption/expiry ngoài scope. Review xác nhận đủ cơ sở lập kế hoạch, không chứng nhận runtime hoặc demo end-to-end.

Trạng thái: **đặc tả demo nội bộ để review và lập kế hoạch; chưa triển khai**. Bốn phần: replay/A3/tick, issuance coins+voucher/cancel, tín hiệu lịch sử trả hàng, kiểm chứng độc lập. Không tạo provider, queue server, HTTP server hay classifier mới. Mục tiêu là nền Python/SQLite ghép A2 hiện có và A1 của Trúc trong hackathon 7 giờ; local entitlement không cộng ví Shopee thật, không có voucher code dùng ngoài hệ thống.

> **Path/interface adaptation - 2026-10-31:** Latest explicit execution rules control paths and worker scheduling. All source additions stay in platform_huy (Truc UI/serve_ui excluded); existing contracts entirely read-only. Task 1 owns dto.py, local migrations, transaction helpers and neutral global command-key metadata lookup. Task 2 MUST reuse logistics_an_nguyen.replay.ReleaseReader unchanged, adding integrity/hash validation and masks around its snapshot, never a replacement reader. Task 3 owns clock/checkpoint only; Task 4 integrates actual A3->A2 plus guard. Two coding workers maximum, private worktrees and non-overlapping files; controller alone wires facade and integrates Git. Approved business decisions below remain unchanged except the explicitly pending blocked-key question.

## 1. Căn cứ, phạm vi và phương án

Nguồn bắt buộc: `AGENTS.md`, `docs/team_plan.md`, `docs/decisions.md`, `contracts/{types.py,params.py,schema_state.sql}`. Căn cứ nghiên cứu: [data/guard](../research/2026-10-31-huy-data-guard.md), [execution và lịch sử returns, mục 10](../research/2026-10-31-huy-execution.md), [test integrity](../research/2026-10-31-agent-test-integrity.md). Các báo cáo nêu schema thực, API A2 và giới hạn bằng chứng; không xem chúng là implementation đã verified.

**Luật hiện hành đã xác nhận:** D1–D5; coins 5% giá trị items, floor1.000, min10.000/max1.000.000, None/0→10.000; voucher cố định10.000 VND. Hai khoản cùng điều kiện: trễ >=2 ngày lịch VN, khách tự yêu cầu TEXT trong chat A1 mở, không lỗi khách/không bất khả kháng. Cho phép nhận cả hai qua **hai authorized Action riêng**, mỗi loại once/order; một call/message không tự kích hoạt hai khoản, khoản này không tiêu thụ quyền khoản kia. Refund/shipping_fee_refund vẫn policy_not_configured. Lịch sử returns chỉ mô tả bằng chứng riêng shop, không score/verdict hoặc denial rule mới. [Decision log](../research/2026-10-31-huy-demo-decisions.md) là căn cứ cập nhật.

Voucher10.000 là policy demo do Huy chọn, không khẳng định Shopee luôn bồi thường mệnh giá đó; xem [nghiên cứu](../research/2026-10-31-shopee-voucher.md). Scope chỉ issuance nội bộ: không redemption/expiry, không tự tạo TTL, minimum spend, mã dùng tại Shopee hoặc lời hứa provider.

**Lựa chọn đã xác nhận và thiết kế áp dụng:** một state DB/run; manual Next+30; business clock tách A2 checkpoint; chat immediate và wall receipt audit riêng; strict source freshness/global feed; sticky proactive deny; evidence-backed human verification theo order. Không TTL tự đặt hoặc quyền human bypass eligibility. Unknown còn lại cần review/no grant, không mặc định clear.

| Phương án | Lợi ích | Chi phí/quyết định |
| --- | --- | --- |
| A. Full snapshot A2 + một SQLite state giao dịch | Tận dụng code có sẵn, restart kiểm chứng được, thư viện chuẩn | Chọn cho bản đầu; đọc lại snapshot mỗi tick, đo trước khi tối ưu |
| B. Cache incremental + health theo carrier/service | Ít đọc hơn, scope outage chi tiết | Thêm cache consistency và thay A2 contract; hoãn |
| C. Queue/provider/saga ngay | Phục vụ external effects sau này | Chưa có transport/rules; vượt 7 giờ, hoãn |

Freshness chọn timestamp nguồn từng business feed thay vì telemetry heartbeat: ít suy diễn nhất theo D3, nhưng sparse feed có thể block proactive dù không outage. Ops chỉ giải thích; không làm business data cũ trở thành mới. Không tự đặt ngưỡng lag/error mới.

## 2. Yêu cầu đánh số và ranh giới sở hữu

1. **R1 — Nguồn:** chỉ đọc hai release DB bằng URI `mode=ro`, `query_only=ON`; không sửa `sim_clock`, schema, index, ledger, không đọc truth/heldout, không sinh world data. Runtime nằm trong `runs/<run_id>/state.sqlite`.
2. **R2 — As-of:** scan visible theo `ingested_at <= T`; cursor dùng nhóm ingestion đã đọc hết. Các stream khác dùng timestamp thực ở bảng nguồn; mask riêng kết cục tương lai. Tất cả datetime aware; state/wire UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`; guaranteed_date giữ ngày VN.
3. **R3 — Validation:** schema/identity hỏng dừng run; visible semantic corruption không được silently drop rồi báo trusted. Không để lỗi semantic chưa visible ảnh hưởng health quá khứ; availability malformed không xác định được cutoff thì fail closed feed/source.
4. **R4 — A3:** đúng ba required feeds A2 hiện có: orders, scan_events, delivery_attempts; health global theo feed. Quá 30 phút nguồn mới stale, không phải >=30. Thiếu/quá 60 phút heartbeat hoặc feed unusable chặn proactive. A3 chỉ siết control, không đụng tiền.
5. **R5 — Tick:** manual clock+attempt durable trước compute; A3 heartbeat/health hoàn tất commit riêng; A2 assessments/questions/progress/watermark/checkpoint công bố atomically khi batch thành công. Failure có durable incident+deny riêng, không success heartbeat giả; retry không nhân progress/output. A1 handoff sau publication, integration còn pending.
6. **R6 — Authority:** Action là request; source/role/ownership từ server wiring/session. Coins chỉ source=a1, voucher chỉ source=rule theo matrix hiện có; A2/A3/LLM không ghi entitlement. Duy nhất public platform_huy.execute_action ghi coins/voucher, không client-minted context.
7. **R7 — Eligibility chung:** explicit customer TEXT trong chat A1-opened, đúng customer/order, late_days>=2 lịch VN, xác định không customer fault/FM, source facts trusted và history once/kind. Human verification có proof được phép resolve unknown theo mục9, không override known exclusion/conflict/stale/provenance/amount/once-kind. Coins tính lại quote, voucher integer10000.
8. **R8 — Atomicity:** cùng key/payload trả persisted result, khác payload/principal conflict. Một coins row và một voucher row tối đa/order trong cùng state authority, độc lập quyền lợi. Receipt success chỉ local SQLite entitlement, không external wallet/provider delivery.
9. **R9 — Cancel:** bước đầu không hủy; xác nhận lần hai bind request/order/customer/version; sau đó vào review runtime. Approval không UPDATE nguồn, không chứng minh carrier đã hủy, không tự hoàn tiền. Client queue/needs_approval không bypass.
10. **R10 — Return signal:** chỉ seller của order đang xem, customer suy từ order; đếm request và DISTINCT order riêng; physical returned scan riêng. Lọc as-of, ghi window/coverage/provenance, không lộ shop khác/PII; không thay fault/coins eligibility.
11. **R11 — Verification:** literal expected từ luật trước code; kiểm output và SQL state thật, crash/concurrency; giữ test người khác. Suite xanh không được dùng làm chứng nhận A1/provider chưa tích hợp.

| Module/file dự kiến | Trách nhiệm / owner |
| --- | --- |
| `platform_huy/sources.py`, `validation.py`, `replay.py` | Read-only source identity, projection bổ sung, validator, ingestion watermark — Huy |
| `platform_huy/state.py`, `tick.py`, `guard.py` | Migration, checkpoint, A2 adapter, heartbeat/control/gate — Huy |
| `platform_huy/execution.py`, `cancellation.py`, `return_history.py` | Permission, evidence, ledger, cancel workflow, authorized counts — Huy |
| `platform_huy/__init__.py`, `platform_huy/dto.py` | Local public exports/types; preserve existing Action/OrderAssessment and all contracts files |
| `platform_huy/migrations/001_platform.sql`, `acceptance_huy/test_taskNN_*.py` | Companion schema and explicitly authorized task-owned tests; no contracts/pytest.ini edits |
| `acceptance_truc/` | Huy viết acceptance cho A1 thật khi Trúc bàn giao seam; hiện pending |
| Existing A2/care modules and tests | Read-only. Explicit user exception authorizes only assigned new acceptance_huy/test_taskNN_*.py; no existing or other task tests changed. |
| `care_truc/`, `platform_huy/ui_prototype/`, `platform_huy/serve_ui.py` | A1/HTTP/auth/UI của Trúc; chỉ bàn giao interface, không sửa |

## 3. Replay/A3/tick: luồng và lỗi

Khởi động xác minh canonical source paths, schema/cột/PK, `quick_check`, manifest/hash một lần mỗi run; lưu identity. Mở source và state bằng connection riêng, không ATTACH writable state vào reader. Không chạy hash/quick_check mỗi tick. FK bật mỗi state connection. Timestamp TEXT chỉ so trực tiếp sau khi invariant offset/precision đã được validator xác nhận; nếu không, parse instant trước cutoff.

| Stream | Availability / source timestamp / mask |
| --- | --- |
| orders | created_at <=T; source=MAX(created_at); mask cancelled_at/actor/reason nếu cancellation còn tương lai |
| scan_events | ingested_at <=T; source=MAX(event_at hợp lệ đã ingest), last_ingested_at tách riêng; event_at > ingested_at là corrupt |
| delivery_attempts | attempt_at <=T; source=MAX(attempt_at); không bịa measured ingestion |
| linehaul_reports | reported_at <=T; text chỉ dữ liệu, không đổi fault hay FM |
| returns | requested_at <=T; trước decided_at mask quyết định/refund; không dùng final status làm timeline refund/physical return |
| compensation_ledger | created_at <=T; tra theo order trực tiếp, không inner join làm mất lịch sử ngoài lát |
| ops | metrics/logs/alerts/deploy_events.ts <=T; webhook received_at <=T và processed_at mask; telemetry scope đúng service |

Không đưa planned trips vào slice đầu vì thiếu timestamp lịch được biết; không nhận bảng mutable tham chiếu như lịch sử đã version. Order thiếu/sai guaranteed_date bị quarantine trước ReleaseAdapter, không lấy ETA thay. Visible corruption liên quan required feed → status corrupt toàn feed; missing nếu không xác lập được nguồn; thứ tự `corrupt > missing > stale > trusted`. Orders hợp lệ vẫn được A2 đánh giá unknown_feed; order không tạo được OrderFacts thì có incident + quarantine list, không assessment bịa. Nếu cấu trúc/availability không thể tạo snapshot an toàn thì rollback tick, không success heartbeat.

Source MAX được tính trên toàn feed visible hợp lệ, không theo một order đứng yên. Một visible corrupt row luôn thắng MAX mới. `checked_at=T`, heartbeat `tick_at=T`, `recorded_at` là wall-clock audit UTC, tuổi nghiệp vụ chỉ dùng simulated clock. Ops failure có incident; không tự chặn feed nghiệp vụ độc lập nếu không có policy dependency, cũng không nâng trusted bằng metric của service khác.

**Manual decision clock:** `simulated_now = demo_clock.current_at`, durable độc lập A2 checkpoint. Bootstrap chỉ lưu start_at; initialize_tick tạo attempt đầu tại start_at (một lần/idempotent); sau đó advance_tick cần replay:advance, expected_clock_version và stable command key. BEGIN IMMEDIATE commit now+30 phút + clock.version+1 + attempt pending + command receipt **trước** A3. Không caller-supplied target time; retry key cũ trả cùng attempt, version race không tăng hai lần. Khi current attempt pending/running, Next mới trả version_conflict; failed attempt cho phép retry_current_tick hoặc Next+30 mới, không rollback clock về last-good. Restart phục hồi now/current attempt; pending/running bị gián đoạn coi degraded và block ngay cho đến resume/retry an toàn, không tự báo success.

Business mutation trước initialize_tick raise run_not_ready/gate false. Sau initialize, inbound/contact-message/handoff có thể nhận dù attempt failed; entitlement/proactive cần current attempt succeeded và nguồn trusted, nếu không blocked tick_unavailable. Giữa hai lần Next, clock đứng yên; chat server tự gán created_at=now và lưu received_at wall UTC audit, phản hồi ngay không đợi tick, không dùng wall10:17 để đọc tương lai sau now10:00. Action.requested_at/opened_at/control.at chỉ audit aware<=now; future reject. record_customer_message không nhận business created_at từ caller; received_at do trusted transport đóng dấu, không tính freshness/eligibility. Evidence.as_of bắt buộc ==now; return-history cho coverage_start<=as_of<=now. Re-read clock/version trong mutation transaction và revalidate nếu đổi. Không wall-clock business logic; timeout dùng monotonic runtime.

Internal run_tick chỉ xử lý current attempt/current_at, không advance; caller tick_at khác now trả tick_sequence_invalid. Đọc kết quả tick cũ dùng getter, không rewind. Retry failed tick cùng now dùng full source snapshot mới từ DB identity cố định; scan delta tính từ **last successful A2 checkpoint** tới now, trọn nhóm ingestion trước watermark. Next sau tick thất bại có thể tạo gap; ProgressTracker hiện có tự reset stationary count khi gap khác30 phút, không bù giả các interval và không sửa thuật toán An.

Một controller runtime/run; run_tick là internal coordinator, Trúc chỉ gọi manual command APIs và read view. Command receipt bind operation/principal/expected_version→stable attempt_id; retry key trả current status của cùng attempt, không advance. retry_current_tick chỉ resume interrupted/failed attempt tại now, retry_count tăng; succeeded trả current result không recompute. Ghi publish so cả clock/version và attempt retry_count để attempt cũ không ghi đè. Reuse completed A3 tại cùng tick/source identity khi chỉ A2 retry; không INSERT heartbeat trùng hoặc rewrite outcome thành success giả. Source identity thay đổi luôn source_invalid/run mới.

Mỗi attempt Huy kiểm trực tiếp mọi raw scan có ingested_at<=T trước khi dùng A2 reader; query A2 có event_at<=T không được che scan corrupt. Huy kiểm join order visible, quarantine/mask xong mới đưa projection an toàn cho adapter. Tạo ProgressTracker mới từ state committed → `ReleaseAdapter(snapshot).orders()` → `tracker.apply(..., tick_at=T, feed_health=health)` → `evaluate_tick(...)`. Dùng đúng `OrderFacts.required_feeds` và `FeedHealth` hiện có. `QuestionStore.save` dùng transaction state; serialized progress lấy adapter Huy round-trip đúng `tracker.records`, không sửa A2. Không dùng A2 CLI/progress.json làm coordinator. Projection dict là bản riêng cho attempt, không hứa frozen sâu.

A3 hoàn tất: transaction commit actual heartbeat/health/incidents và tighten controls, đánh dấu attempt.a3_status=completed; dữ liệu này không bị rollback bởi A2 lỗi sau đó. Feed bad nhưng projection an toàn vẫn gọi A2 với health bad. A3 timeout/exception/unsafe snapshot không ghi heartbeat success; rollback attempt work rồi transaction riêng ghi attempt failed + incident + sticky false. Current pending/failed gate đã block độc lập tuổi heartbeat nên frozen clock không giữ quyền cũ. State unwritable: live gate deny state_unavailable, không claim incident đã persisted; restart bắt buộc đọc/kiểm state, pending attempt vẫn deny.

A2 thành công: BEGIN IMMEDIATE so clock/attempt/checkpoint version; ghi assessments/quarantine/questions/progress/scan watermark/tick_results và A2 checkpoint cùng COMMIT, attempt succeeded. Exception rollback phần A2, bỏ tracker, giữ completed A3 rows; transaction riêng ghi attempt failed/a2_failure+incident+sticky proactive false. Unexpected A2 exception fail toàn batch thật, không invent per-order success hoặc sửa A2. Read view giữ last-good assessment với assessment_current=False/degraded, không dùng nó cấp entitlement hoặc hứa ETA mới. Failure audit trước tick đầu cũng được lưu, không yêu cầu success checkpoint. Busy timeout5s trả state_busy, không success giả hoặc vô hạn retry.

Checkpoint chỉ nghĩa **A2 snapshot/progress/ingestion watermark đã publish**, không là decision clock và không nghĩa A1 chạy. A3 state có thể mới hơn checkpoint. tick_results là durable A1 handoff pending_integration; key `(run_id,tick_at,order_id)` ổn định, reread không tạo Action. Không gọi A1/LLM/network trong transaction, export sau commit. Human release sticky deny chỉ khi current attempt succeeded, A3/feeds trustworthy và không failure mới hơn, luôn audit.

Control duy nhất bản đầu `proactive_contact_allowed`, scope=`global`, bool. Khởi tạo true không vượt gate nguồn; A3 được true→false/false→false, false→true trả `control_relaxation_denied`. Feed hồi phục có thể trusted nhưng control vẫn false. Human có capability `controls:release` mới mở lại; trong transaction kiểm source/heartbeat hiện tại bằng cùng gate bỏ riêng sticky false, audit incident, rồi mở. Không mở từ source text/LLM. Không tạo control tiền mới.

`can_proactively_contact(order_id)` resolve committed dependency list/assessment đúng run, current clock+attempt/failure và A3 health mới nhất <=now. Current pending/failed/current assessment thiếu→false ngay, không dựa heartbeat cũ. Toàn required feeds usable_at(now), heartbeat<=60m, sticky control true. Gate read/authorization serialize cùng clock/control update trong transaction ngắn, kết thúc trước transport; Trúc gọi lại ngay trước open/send. Không hứa thu hồi contact sau transport nhận. Gate không đóng inbound/cancel/handoff; Trúc dùng read view degraded/current để giới hạn lời trả lời.

## 4. Giao diện Python đề xuất

Types below are frozen local dataclasses in platform_huy/dto.py, importing only stdlib and contracts.types. No A2 or platform runtime imports; contracts/__init__.py remains unchanged. Tuple boundaries, canonical JSON and all existing DTO fields/signatures below are preserved. Platform facade/wiring stays in platform_huy; map FeedHealthRecord to existing A2 FeedHealth 1:1 without changing A2 models.

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol
from contracts.types import Action, ActionSource, OrderAssessment

class ExplicitRequestRule(Protocol):
    version: str
    def recognizes(self, body: str) -> bool: ...

@dataclass(frozen=True)
class FeedHealthRecord:
    feed: str
    status: Literal["trusted", "stale", "corrupt", "missing"]
    checked_at: datetime
    source_timestamp: datetime | None
    last_ingested_at: datetime | None

@dataclass(frozen=True)
class SourceIdentity:
    core_sha256: str
    ops_sha256: str
    coverage_start: datetime
    coverage_end: datetime

@dataclass(frozen=True)
class ServerContext:
    principal_id: str
    source: ActionSource | None
    customer_id: str | None
    seller_id: str | None
    capabilities: frozenset[str]

@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason_codes: tuple[str, ...]

@dataclass(frozen=True)
class StoredTick:
    tick_at: datetime
    checkpoint_version: int
    assessments: tuple[OrderAssessment, ...]
    feed_health: tuple[FeedHealthRecord, ...]
    quarantined_order_ids: tuple[str, ...]
    a1_status: Literal["pending_integration"]

@dataclass(frozen=True)
class TickAttempt:
    attempt_id: str
    tick_at: datetime
    clock_version: int
    status: Literal["pending", "running", "succeeded", "failed"]
    a3_status: Literal["pending", "completed", "failed"]
    error_codes: tuple[str, ...]

@dataclass(frozen=True)
class GuardHeartbeatRecord:
    tick_at: datetime
    agent_id: str
    recorded_at: datetime
    proactive_contact_allowed: bool
    reason_codes: tuple[str, ...]

@dataclass(frozen=True)
class CurrentGuard:
    snapshot_tick_at: datetime | None
    a3_status: Literal["missing", "pending", "completed", "failed"]
    heartbeat: GuardHeartbeatRecord | None
    feed_health: tuple[FeedHealthRecord, ...]
    proactive_control_allowed: bool
    gate_scope: Literal["global", "order"]
    order_id: str | None
    effective_proactive_gate: GateDecision

@dataclass(frozen=True)
class CommittedView:
    run_id: str
    current_at: datetime | None
    clock_version: int
    current_attempt: TickAttempt | None
    latest_tick: StoredTick | None
    assessment_current: bool
    failure_codes: tuple[str, ...]
    current_guard: CurrentGuard | None

@dataclass(frozen=True)
class EligibilityReviewDecision:
    responsibility: Literal["carrier", "platform", "unknown"]
    force_majeure: Literal["absent", "present", "unknown"]
    coins_history: Literal["not_granted", "already_granted", "unknown"]
    voucher_history: Literal["not_granted", "already_granted", "unknown"]
    field_evidence_refs: tuple[tuple[str, tuple[str, ...]], ...]
    field_verification_notes: tuple[tuple[str, str], ...]

@dataclass(frozen=True)
class ExecutionResult:
    action_id: str
    decision: Literal["succeeded", "blocked"]
    reason_codes: tuple[str, ...]
    kind: Literal["coins", "voucher", "cancel_request", "eta_notice", "refund", "shipping_fee_refund"]
    amount_xu: int | None
    ledger_id: str | None
    amount_vnd: int | None
    voucher_ledger_id: str | None
    cancel_id: str | None
    replayed: bool

CancelStatus = Literal["awaiting_confirmation", "awaiting_review", "approved", "rejected"]
@dataclass(frozen=True)
class CancellationResult:
    cancel_id: str
    order_id: str
    status: CancelStatus
    confirmation_id: str
    version: int
    replayed: bool

@dataclass(frozen=True)
class ReturnHistorySignal:
    signal_code: Literal["return_history"]
    scope: Literal["seller_visible_release_slice"]
    visible_request_count: int
    visible_order_count_with_requests: int
    physical_returned_order_count: int
    window_start: datetime
    window_end: datetime
    observed_requested_at_min: datetime | None
    observed_requested_at_max: datetime | None
    coverage_complete: Literal[False]
    status_history_available: Literal[False]
    unknown_link_count: int
    evidence_refs: tuple[str, ...]
    review_required: None
    threshold_policy: None

class PlatformError(Exception):
    code: str

class Platform:
    def __init__(self, *, core_path: Path, ops_path: Path, state_path: Path,
                 run_id: str, start_at: datetime,
                 request_rule: ExplicitRequestRule | None = None) -> None: ...
    def close(self) -> None: ...
    def validate_sources(self) -> SourceIdentity: ...
    def initialize_tick(self, *, idempotency_key: str,
                         context: ServerContext) -> TickAttempt: ...
    def advance_tick(self, *, expected_clock_version: int, idempotency_key: str,
                      context: ServerContext) -> TickAttempt: ...
    def retry_current_tick(self, *, expected_clock_version: int, idempotency_key: str,
                            context: ServerContext) -> TickAttempt: ...
    def run_tick(self, *, tick_at: datetime) -> StoredTick: ...
    def get_committed_view(self, *, order_id: str | None = None,
                            context: ServerContext) -> CommittedView: ...
    def can_proactively_contact(self, order_id: str, *,
                                context: ServerContext) -> GateDecision: ...
    def set_proactive_control(self, allowed: bool, *, at: datetime,
                              context: ServerContext, reason: str) -> GateDecision: ...
    def record_contact_opened(self, *, contact_id: str, order_id: str,
                              channel: Literal["chat", "web_voice"], proactive: bool,
                              opened_at: datetime, context: ServerContext) -> None: ...
    def record_customer_message(self, *, message_id: str, contact_id: str,
                                body: str, origin: Literal["text", "voice_transcript"],
                                received_at: datetime, context: ServerContext) -> str: ...
    def record_eligibility_review(self, order_id: str, decision: EligibilityReviewDecision, *,
                                  expected_revision: int, reason: str, evidence_as_of: datetime,
                                  idempotency_key: str, context: ServerContext) -> str: ...
    def withdraw_eligibility_review(self, order_id: str, *, expected_revision: int,
                                    reason: str, idempotency_key: str,
                                    context: ServerContext) -> str: ...
    def get_eligibility_review_revision(self, order_id: str, *,
                                         context: ServerContext) -> int: ...
    def prepare_execution_evidence(self, order_id: str, *, as_of: datetime,
                                   contact_id: str | None = None,
                                   message_id: str | None = None,
                                   context: ServerContext) -> str: ...
    def execute_action(self, action: Action, *, context: ServerContext) -> ExecutionResult: ...
    def request_cancellation(self, order_id: str, *, idempotency_key: str,
                             context: ServerContext) -> CancellationResult: ...
    def confirm_cancellation(self, cancel_id: str, confirmation_id: str, *,
                             expected_version: int, idempotency_key: str,
                             context: ServerContext) -> CancellationResult: ...
    def review_cancellation(self, cancel_id: str, decision: Literal["approve", "reject"], *,
                            expected_version: int, reason: str, idempotency_key: str,
                            context: ServerContext) -> CancellationResult: ...
    def list_review_queue(self, *, context: ServerContext) -> tuple[CancellationResult, ...]: ...
    def get_cancellation(self, cancel_id: str, *,
                          context: ServerContext) -> CancellationResult: ...
    def list_order_actions(self, order_id: str, *, context: ServerContext) -> tuple[ExecutionResult, ...]: ...
    def get_return_history_signal(self, order_id: str, *, as_of: datetime,
                                  context: ServerContext) -> ReturnHistorySignal: ...

def bind_platform(platform: Platform) -> None: ...
def execute_action(action: Action, *, context: ServerContext) -> ExecutionResult: ...
```

`bind_platform` chỉ startup bind active run; khác run đang active→validation_error. Module execute_action delegate Platform đó. Capability: replay:advance (human operator, không source LLM), state:read, eligibility:review (human), actions:coins (a1), actions:voucher (rule), cancel:request/confirm/read/review, actions:read, returns:read, contacts:write, controls:tighten/release. Kiểm source+capability+ownership. get_committed_view không advance/run batch; customer/seller chỉ own-order assessment, operator state:read mới all-orders. Voucher result amount_vnd10000/voucher_ledger_id, coin fields null; coins amount_xu/ledger_id, voucher fields null; blocked không effect IDs. Context không sandbox trước malicious Python có DB access.

get_committed_view đọc clock/attempt/latest A2 snapshot/current guard/control/review head trong **một SQLite read transaction**, resolve ownership/capability trong cùng snapshot trước serialize; không ghép nhiều independent queries qua state đang đổi. current_guard đầy đủ chỉ cho state:read, principal own-order không có quyền đó nhận null (không leak ops), assessment lọc own-order. CurrentGuard là A3 của current attempt, không lấy feed_health từ StoredTick: completed→snapshot_tick_at=current now+actual heartbeat/feeds dù A2 failed hoặc chưa từng publish; pending/failed/missing→snapshot_tick_at=null/heartbeat=null/feeds=(), status và effective gate false có reason thật. Sticky control và gate tính tại cùng snapshot riêng khỏi health lịch sử. Gate global chỉ prerequisites toàn run; gate order kiểm thêm committed assessment/dependencies của order. StoredTick.feed_health luôn giữ nguyên health dùng tại publication, không relabel thành current.

PlatformError codes: validation_error, permission_denied, not_found, idempotency_conflict, version_conflict, state_busy, state_unavailable, source_invalid, tick_sequence_invalid, run_not_ready. Unauthorized order→not_found. Current tick failure/pending proactive→GateDecision false, entitlement→blocked tick_unavailable; well-formed business denial có receipt. Manual command hoàn tất trả TickAttempt succeeded/failed thật; state không ghi được raise state_unavailable, không synthetic success. Trúc map HTTP; Huy không chọn framework.

## 5. State và tương thích migration

Giữ nguyên tám bảng v0 và CHECK/FK/UNIQUE hiện có; không thêm trigger khiến fixture INSERT v0 của acceptance_huy hỏng. Production services thực thi invariant bổ sung. `schema_state.sql` vẫn bootstrap v0, migration 001 chạy trước business transaction; không `executescript` giữa tick/action. Chỉ một state DB/run, không đổi PK heartbeat/health hiện có.

Trong bảng schema dưới đây, trường không ghi kiểu là TEXT; singleton/version là INTEGER, JSON/hash/timestamp lưu TEXT; nullable chỉ những trường ghi nullable. Khóa/FK và enum được migration thực thi; service kiểm cross-row order/customer relationships.

| Bảng bổ sung | Schema bắt buộc (mọi ID/key NOT NULL, JSON CHECK json_valid) |
| --- | --- |
| schema_migrations | version INTEGER PRIMARY KEY, applied_at TEXT |
| run_metadata | singleton INTEGER PK CHECK=1, run_id UNIQUE, source_identity_json, start_at, policy_version=`huy-demo-v1` |
| replay_checkpoint | singleton INTEGER PK CHECK=1, tick_at nullable, scan_watermark nullable, version INTEGER >=0 |
| demo_clock | singleton INTEGER PK CHECK=1, current_at nullable, version INTEGER>=0, current_attempt_id nullable FK tick_attempts; độc lập replay_checkpoint |
| tick_attempts | attempt_id PK, tick_at UNIQUE, clock_version INTEGER, status enum TickAttempt.status, a3_status enum, retry_count INTEGER>=0, errors_json, started_wall_at, finished_wall_at nullable |
| replay_commands | idempotency_key PK, principal_id, request_hash, attempt_id FK, result_json; key+version dedup initialize/advance/retry, replay không tăng clock |
| tick_results | tick_at PK, result_json, result_sha256; result có assessments/health/quarantined IDs/A1 pending và required_feeds_by_order từ OrderFacts committed |
| a2_progress | singleton INTEGER PK CHECK=1, tick_at, records_json; canonical round-trip tracker.records |
| customer_messages | message_id PK, contact_id FK contact_log, order_id, customer_id, origin enum text/voice_transcript, created_at business now, received_at wall audit, body, request_code nullable late_compensation, request_rule_version nullable, recorded_by |
| execution_evidence | evidence_id PK, order_id, contact_id FK nullable, message_id FK nullable, assessment_at, visible_at, policy_version, payload_json, sha256, created_by |
| action_receipts | action_id PK FK outbox, request_hash, principal_id, attested_source, evidence_id FK nullable, decision_code, result_json, decided_at |
| voucher_ledger | voucher_ledger_id PK, idempotency_key UNIQUE, order_id UNIQUE, action_id UNIQUE FK outbox, contact_id FK contact_log, face_value_vnd INTEGER CHECK typeof=integer AND=10000, policy_version, created_at; chỉ local issuance |
| eligibility_reviews | review_id PK, order_id, revision INTEGER>=1, state enum active/withdrawn, source_identity_json, evidence_as_of, material_fingerprints_json (common/coins_history/voucher_history), decision_json, evidence_refs_json, reason, reviewed_by, reviewed_wall_at, idempotency_key UNIQUE, request_hash; UNIQUE(order_id,revision), immutable audit |
| cancel_requests | cancel_id PK, request_action_id UNIQUE FK outbox, order_id, customer_id, status CHECK CancelStatus, confirmation_id UNIQUE, version>=1, order_snapshot_sha256, requested_at, confirmed_at nullable, reviewed_at/by/reason nullable |
| workflow_commands | idempotency_key PK, request_hash, principal_id, cancel_id FK, result_json, created_at; confirm/review durable retries |

Migration kiểm version; v0→001 transactional, chạy lại no-op; version cao hơn hỗ trợ trả source/state error và không ghi. State cũ thiếu metadata chỉ adopt khi tám bảng v0 rỗng; state có dữ liệu không rõ source/run trả source_invalid, không backfill provenance giả. FK luôn ON. Giữ nguyên ledger_new coins v0 và UNIQUE(order_id) của nó; voucher_ledger có UNIQUE(order_id) riêng, không ghi voucher vào amount_xu, không UNIQUE(order_id) dùng chung hai kind. Không migration source hoặc delivery_outbox/provider schema; không columns redemption/expiry.

Evidence payload gồm source identity/as_of, order/customer/seller/items value, assessment/hash, contact/message provenance, fault_verification=verified|unknown|conflicting, force_majeure=present|absent|unknown và refs. `history_by_kind` bắt buộc có hai keys coins/voucher, mỗi entry `{classification: clear|already_granted|ambiguous|unavailable, source_refs: tuple[str,...], reviewed_refs: tuple[str,...]}`; không scalar dùng chung. `selected_review` là null hoặc `{review_id, revision, common_fingerprint, coins_history_fingerprint, voucher_history_fingerprint}` do server resolve; immutable hash chỉ định danh, không quyền vĩnh viễn. Local runtime ledgers kiểm live ngoài review fingerprint.

**Explicit request seam:** trusted server startup truyền `request_rule` là adapter deterministic/versioned thuộc A1 của Trúc; không deserialize callback/version từ HTTP, không dùng LLM verdict, không tự thêm keyword matcher thay A1. `record_customer_message` với contacts:write xác minh authenticated customer và contact/order/origin; origin lấy từ trusted transport event (typed customer text hoặc voice transcript), không từ client claim. Service lưu body gốc rồi gọi rule.recognizes(body) chỉ khi origin=text và contact A1-opened chat. True mới mint request_code=late_compensation và request_rule_version; False/không adapter để cả hai null. Adapter error abort transaction với source_invalid, không mint signal. Client/A1 output JSON không có quyền gửi request_code; evidence builder chỉ resolve giá trị do service đã mint. Thiếu signal → blocked invalid_request_provenance. Đây là API nối rule thật, không khẳng định A1 đã có; tests fixture rule chỉ ở test construction, không client-accessible attestation endpoint.

`record_contact_opened` cần contacts:write và ownership; proactive=true bắt buộc source=a1 và kiểm gate tại server now, initiated_by=A1 do server gán; inbound source app gán customer. opened_at chỉ event audit <=now. Cùng contact_id/cùng facts no-op, khác facts conflict; record message tương tự immutable bằng ID. Ghi contact không giả external provider đã mở; adapter chỉ gọi sau event mở phiên thật. Evidence builder tự resolve latest committed assessment và nguồn tại now (as_of phải bằng now), không nhận eligibility facts từ khách; mặc định FM unknown như mục 6.

prepare_execution_evidence không contact/message chỉ tạo order-authorized snapshot cho cancel_request từ customer/app/A1 có cancel:request; không request signal nên không thể cấp coins/voucher. Khi truyền contact/message phải cả hai và kiểm bindings; hai kind đều cần provenance. Builder resolve valid eligibility review mục9, không nhận reviewed fields từ Action. Gate đọc committed required_feeds_by_order, không API dependency input.

## 6. Executor coins+voucher và cancellation

Executor resolve evidence và source identity/as_of server-side; so message.order/contact.order/evidence.order/action.order và customer. Message phải nằm sau opened_at, trước closed_at nếu có, không future; contact A1-opened channel chat. `origin=voice_transcript` không được text request. Không tự đặt TTL phiên; closed session có message hợp lệ vẫn được kiểm theo facts tại decision, không phải miễn kiểm freshness.

Evidence phải thuộc latest committed assessment của order, không future; executor kiểm lại required FeedHealth.usable_at(simulated_now) và visible source facts, không dùng historical health boolean để chứng minh tài chính hiện tại. Không áp heartbeat proactive thành lệnh cấm mọi money request; thiếu current financial evidence riêng vẫn fail closed.

Coins dùng `late_xu_for` hiện có nhưng independently kiểm quote; int chính xác, không bool/float/âm. Action.amount_vnd với kind coins mang số xu vì compatibility, ledger.amount_xu là unit thật; không đặt tỷ giá. Late_days giữ cách A2: max(0, date_VN(delivered_at hoặc T) − guaranteed_date), không đổi sang 48h. Guaranteed 29/10, T=31/10 00:00 VN →2. Không ép status chỉ `late`: fault/FM/health/facts phải đủ, exception không tự được cấp hoặc tự bị loại bằng luật chưa duyệt.

History gate theo kind: ledger_new chỉ coins, voucher_ledger chỉ voucher; visible source.kind coins/voucher tiêu thụ đúng kind, refund/shipping_fee_refund không tiêu thụ hai quyền. Không phát minh voucher programmes hoặc blanket ambiguity. Unknown/malformed source kind→history_policy_unknown, read error→history_unavailable trừ khi human review có proof hợp lệ resolve unknown classification; không override ledger đã biết hoặc biến read failure hiện tại thành history rỗng. FM absent cần evidence-backed review mục9, không suy thiếu cảnh báo hoặc carrier fault. Human review không miễn freshness hoặc A1 signal.

Canonical semantic hash gồm principal/source/order/kind/amount/evidence_ref/confirmation_id. Exclude action_id, requested_at, queue, needs_approval; requested_at chỉ audit, không chọn as-of. Cùng key retry trả receipt cũ. Queue server-derived local_coins/local_voucher/cancel_review/local_notice, không broker. eta_notice chỉ local intent, không delivered; proactive phải qua current gate khi nối transport.

Same action_id with changed key conflicts; legacy outbox without trusted receipt cannot imply success. Shared command-key namespace remains global. Pending Huy decision: earlier immutable blocked receipt/new-key rule conflicts with fixed financial keys xu:{order_id}/voucher:{order_id}; do not implement blocked-key consumption until answered. Successful receipt replay remains immutable. Human review never mints A1/rule authority.

Mỗi kind dùng BEGIN IMMEDIATE: authority+key/hash→nếu receipt tồn tại trả nguyên result trước khi recheck facts/review mới→nếu request mới re-resolve latest review revision/state và so selected_review trong prepared evidence→same source/provenance/freshness gates→history/local ledger đúng kind→outbox+receipt+effect→COMMIT. Revision đổi/withdraw sau prepare→blocked eligibility_review_changed, không fallback hoặc dùng snapshot clearance cũ; caller phải prepare lại để thấy latest unknown/present. Review mutation cũng BEGIN IMMEDIATE nên không chen giữa revalidation và grant. Voucher integer10000/coins quote; sai amount blocked amount_mismatch. Crash trước commit rollback, receipt retry immutable kể cả review đã bị rút. Production keys are fixed per kind/order; canonical-key duplicate replays success, changed semantics conflict, and per-kind ledger UNIQUE(order_id) is the final duplicate guard; coins/voucher độc lập. Hai run/reset không wallet authority chung.

Handoff Trúc: A1 transport/rule adapter tạo customer request signal thật; server-bound a1 entrypoint gọi execute_action cho coins, server-bound platform rule entrypoint gọi cùng cổng cho voucher, có thể dùng cùng evidence_ref và key riêng `xu:{order_id}` / `voucher:{order_id}`. Mỗi action chỉ cấp đúng kind được yêu cầu; **không tự phát voucher sau coins hoặc auto dual-grant từ một call**. Demo cấp hai khoản dùng hai action rõ ràng; partial success retry kind còn thiếu cùng key, không phát lại kind đã cấp/bảo đảm batch atomicity. Voucher rule không LLM/không bypass eligibility. Trúc không mint rule source từ JSON; Huy không viết A1/HTTP thay owner.

Refund/shipping_fee_refund với authority hợp lệ vẫn blocked policy_not_configured, không ledger; source sai permission_denied trước. A3 không có entitlement capability. Proactive control không blanket-ban inbound/cancel, nhưng stale/conflicting financial facts vẫn financial_evidence_untrusted cho cả coins/voucher.

Cancellation dùng hai lượt/API calls riêng: request → awaiting_confirmation (version=1, confirmation_id random mới); confirm đúng principal/customer/order/id/version → awaiting_review (version=2); reviewer có `cancel:review`, reason không rỗng → approved/rejected (version=3). Request Action amount=0, queue/needs_approval do gate ấn định. `execute_action(cancel_request)` với evidence order-authorized mở cùng workflow, không tự consume confirmation; dedicated methods gọi cùng private persistence. ExecutionResult.cancel_id chứa ID workflow durable; kind khác hoặc cancel bị blocked thì null.

`list_order_actions` và retry execute_action trả immutable receipt của request ban đầu, gồm cancel_id, không giả nó là current workflow. `get_cancellation(cancel_id)` trả current CancellationResult gồm confirmation_id/version/status, cho customer có cancel:read đúng customer của order hoặc A1 server được delegate cho customer đó; reviewer dùng cancel:review riêng. Customer không cần và không được vào list_review_queue. Lost response/restart: retry Action cùng key lấy action/result/cancel_id cũ, hoặc actions:read own order lấy cancel_id từ history → get_cancellation → confirm → get_cancellation xem awaiting_review/approved/rejected. Không SQL trực tiếp hoặc tạo request mới chỉ để recovery; wrong customer trả not_found. Stable receipt không lộ confirmation cho bên khác.

Confirmation_id là identifier bind state, **không bearer authorization secret**; authenticated customer và version vẫn bắt buộc. Chỉ ID được phát cho request đó mới hợp lệ; first request không đồng thời là confirmation. Adapter Trúc phải bảo đảm separate customer affirmative turn/click, không dùng message khởi tạo làm lần hai. Không expiry thời gian tự đặt; thay đổi visible order snapshot (cancellation/terminal logistics facts) làm `version_conflict`, yêu cầu request mới và confirm lại, không suy carrier cancellation permission. Mỗi command key retry trả persisted result; key đổi payload/principal conflict; confirmation đã consume với key mới trả version_conflict, không review row thứ hai. Reviewer không tự nhập amount; approval không tạo refund. Không claim đơn nguồn hoặc carrier đã hủy.

Task 9 CLI retry recovery resolves the original authoritative stored Action/evidence before preparing any new evidence. recovery.recover_action(key, *, order_id, kind, contact_id, message_id, context) -> Action | None validates original principal/source/order/kind/contact/message bindings using outbox + action_receipts + execution_evidence, reconstructs and returns the exact original Action/evidence_ref/amount without executing it. The CLI caller invokes the real executor exactly once with the returned Action. Successful receipt replay remains identical after NEXT or review withdrawal. Only absent key prepares current evidence; changed semantics conflict, and a new voucher request checks current authority. No semantic-hash weakening or trusted legacy success. Task 1 lookup_key returns metadata only, does not decide blocked-key policy.

## 7. Tín hiệu lịch sử trả hàng

Huy resolve customer_id/seller_id từ order visible; context.seller_id phải khớp và có returns:read. Join returns→orders bằng order_id; candidate cùng customer, cùng seller, orders.created_at và returns.requested_at <=as_of. Window là [SourceIdentity.coverage_start, as_of] của release slice (manifest/audit coverage được verify startup), không tự chọn lookback 30/90 ngày, không dùng observed min thay coverage start. Từ chối as_of ngoài coverage/current committed replay time bằng validation_error.

visible_request_count đếm return_id, visible_order_count_with_requests đếm DISTINCT order_id. physical_returned_order_count đếm DISTINCT order cùng scope có scan status=`returned`, event_at<=ingested_at<=as_of; không cần return request row để chứng minh scan, không cộng returning/return_failed/cancelled. Các loại có thể overlap và không cộng làm tổng “lần hoàn”. evidence_refs gồm định danh returns và returned scans đã visible; không body/names/phone/address. Trúc hiển thị nhãn riêng “yêu cầu trả”/“đơn có yêu cầu”/“đơn có scan đã trả”.

Source returns không có ingested_at/returned_at/status history: dùng requested_at là quy ước availability, luôn status_history_available=False, không tuyên bố lịch sử refund/approved transition. coverage_complete=False vì chỉ lát release; observed request min/max nullable. Nếu query/schema lỗi raise source_invalid thay vì count=0; malformed/missing linkage trong scope đã xác định tăng unknown_link_count và không tính như valid request; linkage không thể xác định seller không được tiết lộ cho shop, ghi internal incident. Zero chỉ nghĩa không thấy bằng chứng hợp lệ trong phạm vi, không nghĩa chưa từng trả hàng.

`review_required=None`, `threshold_policy=None` luôn giữ; không fraud label, ratio, threshold hoặc automatic review/denial. Count cao không đổi A2 fault, eligibility hay cancel decision. `reason='fake'` là lý do về hàng được yêu cầu trả, không kết luận khách gian lận.

## 8. Ma trận kiểm chứng và điều kiện hoàn thành

Mọi expected dưới đây là literal oracle từ spec, không gọi implementation tính expected. Mỗi negative case giữ các gate khác hợp lệ và assert ledger/outbox/receipt/confirmation state trước/sau. SQLite concurrency dùng hai connection cùng file, không hai :memory: DB độc lập. QuestionStore chỉ chấp nhận file state dưới repository runs/: tick integration/concurrency dùng unique temp directory trong runs/ và cleanup; ordinary tmp_path chỉ dùng module không tạo QuestionStore. Không nới guard A2 để fixtures chạy.

| Case | Expected chính xác |
| --- | --- |
| UPDATE sim_clock/CREATE INDEX qua source; full integration | SQLite từ chối; SHA256 trước/sau không đổi; runtime state ghi được |
| Scan event trước T, ingestion T+1s; 12 scan chung ingestion, batch nhỏ | T không thấy; tick sau thấy; đủ 12 IDs đúng một lần; watermark không dừng giữa nhóm |
| Scan event 10:00, ingested 11:00, T11:00; fresh payment metric | source_timestamp10:00/last_ingested11:00/status stale; payment không đổi kết quả |
| Source age 29:59 /30:00 /30:00.000001 | trusted/trusted/stale nếu các kiểm khác hợp lệ |
| Heartbeat thiếu /59:59 /60:00 /60:00.000001 | gate false/qua kiểm tuổi/qua kiểm tuổi/false; feed vẫn kiểm độc lập |
| Visible event_at>ingested_at; malformed availability; future semantic error | corrupt và block; fail closed nguồn; lỗi future không xuất incident quá khứ |
| Future cancellation/return decision/webhook processed; future order join | trường tương lai null/masked; future order không vào snapshot/signal |
| Sticky false, feed phục hồi; A3 mở; human thiếu trust mở | false vẫn giữ; control_relaxation_denied; GateDecision false |
| A3 completed rồi A2 crash; A3 timeout; failure transaction thành công | A3 rows giữ, A2 checkpoint/progress cũ; không heartbeat success mới; failed+incident+sticky false durable |
| initializeT, NextT+30 fail, restart, retry key Next; Next mới sau failed | nowT+30/failed giữ nguyên; retry key vẫnT+30; key mới+expected version tớiT+60, không bù stationary interval |
| Concurrent/double click Next cùng version hoặc retry same key | chỉ một clock+30/attempt; loser version_conflict hoặc persisted command, không +60 |
| Trước initialize mutation/gate; now10:00 wall10:17 chat text | run_not_ready/false; business created_at10:00/received_at wall10:17, response không chờ Next |
| Backdated opened_at/control.at current feed corrupt; evidence.as_of cũ; caller targettick khác now | gate false hiện tại; validation_error; tick_sequence_invalid; không chọn healthy quá khứ |
| State unwritable lúc A3 fail; restart pending attempt | state_unavailable+live proactive false, không claim persisted incident; pending vẫn false sau restart |
| Gate order dependency attempts degraded, caller muốn bỏ attempts | signature chỉ order_id, committed required feeds vẫn giữ attempts; allowed=False |
| Fresh process import contracts rồi A2.models, và ngược lại | cả hai subprocess exit0; shared DTO không runtime-import A2 |
| Coins eligible verified fixture, value239999/None/0/20154000 | một ledger 11000/10000/10000/1000000 tương ứng; unit xu |
| Cùng order/evidence đủ eligibility, coins source=a1 và voucher source=rule | ledger_new1 + voucher_ledger1, face_value10000 VND; hai receipt riêng, không external effects |
| Voucher source=a1 hoặc app giả rule; amount9999/bool/float | permission_denied; amount_mismatch/validation_error; voucher_ledger delta0 |
| Retry voucher cùng key; hai key voucher race; coins đã có nhưng voucher chưa | persisted receipt, voucher1; một succeeded+một already_granted; voucher vẫn được xét/grant độc lập |
| Fail sau voucher insert trước receipt; hai action demo coins committed nhưng voucher response mất | rollback voucher0 rồi retry1; coins1/voucher1 sau recovery, không duplicate coins |
| Voice/customer-opened chat/late_days1/FM present cho voucher | invalid_request_provenance/invalid_request_provenance/late_days_insufficient/force_majeure; voucher0 |
| Human review unknown responsibility/FM có structured refs; empty proof/known customerfault/FM/conflict | immutable review ID/audit; validation_error hoặc review_conflicts_with_evidence, không grant |
| Review reuse sau unrelated global tick; material fault/history/source identity đổi | không refresh chỉ vì timestamp; review invalidated/eligibility_review_required, ledger0 |
| now giữ nguyên: review r1 absent→prepare E→r2 withdrawn→first execute(E) | blocked eligibility_review_changed; coins0/voucher0, không fallback r1 |
| r1 valid→coins commit→r2 all-unknown hoặc FM present→voucher(E cũ); coins cùng key retry | voucher blocked eligibility_review_changed; coin receipt/result cũ replayed=True, coins1/voucher0 |
| A3 completed T+30/A2 fail sau A2 snapshotT; và first A3 completed/A2 fail chưa snapshot | current_guard T+30 actual heartbeat/feeds +gate false, StoredTick giữT; current_guard actual firstT, latest_tick=null |
| Current A3 pending/failed; concurrent Next trong lúc get view; own-order caller không state:read | no fabricated heartbeat/feeds, gate false; một consistent version; current_guard=null/own assessment only |
| Amount bool/float/âm; action amount sai quote | validation_error hoặc blocked amount_mismatch; ledger delta0 |
| Guaranteed29/10, T31/10 00:00 VN; T30/10 23:59 VN | late_days2 đủ riêng late gate; late_days1 blocked late_days_insufficient |
| App spoof a1; voice transcript; customer-opened chat; other-order message | permission_denied; invalid_request_provenance; invalid_request_provenance; evidence_binding_invalid; ledger0 |
| A1 request adapter absent/False; client supplied request_code; deterministic adapter True, valid text | persisted request_code null/null; unknown request field rejected by HTTP adapter; only trusted service path mints late_compensation; tiền vẫn qua all gates |
| Customer fault/FM present/FM unknown/history unreadable/unknown source kind | blocked customer_fault/force_majeure/force_majeure_unknown/history_unavailable/history_policy_unknown; ledger0 |
| Visible source voucher; visible source coins; visible refund/shipping_fee_refund | chỉ voucher already_granted; chỉ coins already_granted; không tiêu thụ quyền coins/voucher; không blanket history block |
| Same key/same request; same key changed order/amount/evidence/principal | persisted action/result replayed=True, ledger1; idempotency_conflict, không overwrite |
| Two keys one order concurrent; fault giữa ledger/receipt; lost response | một succeeded+một already_granted, ledger1; rollback0 rồi retry1; retry vẫn1 |
| Refund/shipping refund authorized; source reviewer tự khai từ app | blocked policy_not_configured, cả hai entitlement ledgers delta0; permission_denied |
| Cancel request caller needs_approval=False; valid confirm; approve | awaiting_confirmation/v1; awaiting_review/v2; approved/v3; source DB/ledger không đổi |
| execute_action cancel → lost response/restart → own-key retry/history → get_cancellation → confirm → own getter | cùng cancel_id, v1 rồi v2, current workflow đọc được bằng cancel:read; không reviewer privilege; order/ledger không đổi |
| Wrong customer/order/confirmation; stale version; repeat consumed confirm new key | not_found hoặc version_conflict; version_conflict; version_conflict; không duplicate workflow |
| Two return requests same order + one returned scan; future request | request_count2/order_count1/physical_count1; future không tăng |
| Canceled order/returning/return_failed; final returns refunded before decision visible | physical_count0 cho các status đó; không lộ refund/final status |
| Other seller; missing known-scope link; high count | not_found; unknown_link_count tăng không fake zero; review_required/threshold_policy vẫn None và coins unchanged |

Execute through the adapted plan: Task 1 alone, Task 2 sequential, waves 3+5, 6+7, 4+8, then 9. New tests only acceptance_huy/test_taskNN_*.py, no existing tests or pytest.ini changes. Task 3 clock/checkpoint only; Task 4 actual A3/A2/guard integration. Component fixtures are explicitly labeled; full public pipeline evidence comes from Task 4.

Reviewer sạch nhận spec/public contracts trước implementer narrative, tự lập expected/missing cases; sau đó đọc diff/test/state evidence. Controller chạy negative controls trên bản sao Huy-owned: đổi >30 thành >=30, dùng ingestion thay source age, bỏ once/order, bỏ source binding, đổi voice thành text; test tương ứng phải fail bởi assert nghiệp vụ. Không mutate checkout, source hoặc owner khác; không cài mutation tool/coverage dependency mới. Giữ collected/pass/fail/skip/xfail/exit, không sửa expected theo output sai hay thêm skip để gọi done.

Acceptance hoàn thành phần Huy khi import contracts, unit/integration mới, acceptance hiện có và diff checks thực sự pass; source hashes giữ nguyên; restart/concurrency/idempotency và authorization negative cases có evidence. Báo command/revision/counts/exit và phạm vi chưa thử. Dữ liệu fixture chỉ trong temp/in-memory, không vào release/replay world.

**Chưa được gọi hoàn thành:** acceptance_truc chờ A1 thật intents/rules/validator/handoff/cancel second turn/text-vs-voice/gateway; không rewrite A1, mock mất executor hoặc skip để pass. Positive demo cần actual audited review/customer text, không chỉ fixture. External wallet/provider, voucher redemption/expiry, Trúc voice/HTTP/auth/UI ngoài phần Huy. Approved cancel chỉ runtime workflow; issuance record không hứa coupon thật có hiệu lực vĩnh viễn.

## 9. Human verification, demo slices và bàn giao

Huy đã chọn manual Next+30 và nhân viên xác minh có proof theo order/audit, không đợi classifier mới hoặc dùng fixture như nguồn thật. [Main review](../research/2026-10-31-huy-demo-main-review.md) và [orchestration](../research/2026-10-31-agent-orchestration.md) là căn cứ tách clock/A3 outcome/A2 publication mục3.

record_eligibility_review cần human eligibility:review, reason, evidence_as_of=now/source identity đúng run. Exact fields responsibility=carrier|platform|unknown, FM=absent|present|unknown, coins_history/voucher_history=not_granted|already_granted|unknown, field refs/notes; không amount/late override/approve_all. Map key chỉ bốn decision fields, không duplicate. Field khác unknown cần refs visible structured facts và note giải thích phương pháp/căn cứ, không chỉ “đã duyệt”. Service kiểm resolvability/contradictions và lưu immutable audit; human chịu trách nhiệm proof thực chất, validator không tự chứng minh FM absent. Driver/ticket text riêng không structured proof. Thiếu proof→unknown/eligibility_review_required.

**Supersession tối thiểu:** mỗi review là **full replacement cả bốn fields**, không patch. Trong BEGIN IMMEDIATE kiểm expected_revision (0 nếu chưa có), append revision=max(order revisions)+1, UNIQUE(order_id,revision); thứ tự theo INTEGER này, không simulation/wall timestamp. Getter revision chỉ human eligibility:review, trả0 nếu absent và authorized. Latest revision luôn là head kể cả unknown/present/fingerprint invalid; không tìm “latest verified” phía sau. withdraw_eligibility_review append revision state=withdrawn với cả bốn fields unknown, reason/audit và expected_revision; không xóa record/khôi phục clearance cũ. Full replacement active có unknown cũng thu hồi field clearance cũ. Request key retry trả review ID cũ, không append revision lần hai. Prepare bind head ID/revision; execute recheck head trong effect transaction như mục6; future transaction chỉ nhận head đang có, review cũ không giữ quyền sau withdrawal.

Human resolve unknown responsibility/FM/history bằng proof; không override known customerfault, known FM present, conflicting facts, future data, current corrupt/stale/missing feed/read failure, text/voice provenance, >=2 ngày, amount hoặc already-granted kind. Carrier/platform responsibility không tự chứng minh FM absent, cần field proof riêng. Review không mint Action/source/ledger; execution vẫn a1/rule đúng kind. Unknown không tự quy có/không FM hoặc fraud/customerfault.

Server common fingerprint gồm source identity/order/customer, guarantee/items value và material fault/FM/terminal facts/proof applicability; history fingerprint riêng mỗi kind. Responsibility phụ thuộc structured delivery attempts/scans/call facts; FM phụ thuộc cited external/ops facts và note xác minh applicable order/incident scope; mỗi history field phụ thuộc source ledger đúng order/kind + refs phân loại unknown liên quan kind đó. Không unrelated rows/timestamps/global tick. Builder chỉ đọc current head, kiểm fingerprints/visibility của fields cần cho kind; head unknown/withdrawn/present không fallback old verified. Material facts/proof scope đổi→field invalid; tick đơn thuần không ép refresh. Local ledgers kiểm live ngoài fingerprint: coin grant không invalid voucher review; source voucher mới chỉ ảnh hưởng voucher-history. Replacing head là authority change dù material hash giống nhau. Contact/message/current freshness vẫn check mỗi execute; không TTL/human override.

Evidence resolver allowlist: `source://core/<table>/<percent-encoded-pk>` cho orders, scan_events, delivery_attempts, compensation_ledger, external_events; `source://ops/<table>/<percent-encoded-pk>` cho logs/alerts; metrics dùng encoded `(ts,service_id,metric)` ba path components. Resolve đúng run source identity/read-only/as_of, parse original timestamp/structured columns, reject unknown namespace/table/ID/future/cross-order refs (global FM/ops refs phải chứng minh liên quan order trong note). Không mở URL/network/file tùy ý hoặc parse role trong ref. Runtime `evidence://<evidence_id>` chỉ immutable service record đúng order/source/as_of; prior review ID chỉ audit, không thay latest-head authority. Material payload lưu resolved facts/hash, không chỉ opaque strings.

Demo slices: D0 Next→committed assessment/health/view; D1 runtime fault→durable failure+proactive deny, inbound/handoff tiếp tục; D2 cancel request→confirm riêng→review/recovery; D3 shop counts; D4 audited review+real A1 text→hai action riêng→hai entitlement rows/retry. [Candidate release](../research/2026-10-31-huy-demo-cases.md): order261021ZS7E76FW tại2026-10-24T16:00+07, guarantee22/10/value525000 cho quote literal26000 xu+voucher10000. Fresh feeds/no visible failed attempt/ledger không chứng minh fault/FM; chỉ grant sau valid review/provenance. Báo cáo case chưa có actual human verification note; plan/demo phải nhận note thật từ staff, không generate proof hoặc hardcode eligible. Returns same customer/shop release tối đa1, không tạo repeated-return story giả.

Bàn giao Trúc: get_committed_view có run/currentclock/attempt/latestcutoff/version/current-vs-degraded assessment/health; initialize/advance/retry cần operator capability/key; transport đóng received_at audit, platform gán business now; source-bound execution a1/rule; cancel getter/shop counts. Trúc sở hữu ordered turns, actual handoff record/API, rules/validator, auth/UI/voice và transport gọi current gate. Huy không rewrite A1/A2; trước integration thật chỉ báo Python foundation, không full end-to-end demo.
