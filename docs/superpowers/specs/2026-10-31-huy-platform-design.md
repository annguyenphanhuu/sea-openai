# Thiết kế platform Huy, bản đầu — 31/10/2026

Trạng thái: **đặc tả để review và lập kế hoạch; chưa triển khai**. Đây là một hệ thống nhỏ gồm bốn phần theo thứ tự: replay/A3/tick, executor/cancel, tín hiệu lịch sử trả hàng, kiểm chứng độc lập. Không tạo provider, queue server, HTTP server hay classifier mới. Mục tiêu là nền Python/SQLite có thể ghép với A2 hiện có và A1 do Trúc cung cấp trong hackathon 7 giờ.

## 1. Căn cứ, phạm vi và phương án

Nguồn bắt buộc: `AGENTS.md`, `docs/team_plan.md`, `docs/decisions.md`, `contracts/{types.py,params.py,schema_state.sql}`. Căn cứ nghiên cứu: [data/guard](../research/2026-10-31-huy-data-guard.md), [execution và lịch sử returns, mục 10](../research/2026-10-31-huy-execution.md), [test integrity](../research/2026-10-31-agent-test-integrity.md). Các báo cáo nêu schema thực, API A2 và giới hạn bằng chứng; không xem chúng là implementation đã verified.

**Luật người dùng đã chốt:** D1–D5; scope coins + cancel; coins 5% giá trị items, floor 1.000, min 10.000/max 1.000.000, None/0 → 10.000; voucher/refund/shipping_fee_refund nhận diện nhưng `policy_not_configured`. Lịch sử trả hàng chỉ hiển thị số lần có bằng chứng để shop tự đánh giá, không ngưỡng, score, verdict gian lận hoặc điều kiện từ chối bồi thường mới.

**Ghi chú policy đang chờ quyết định — voucher:** sau khi duyệt spec, Huy đề xuất mệnh giá **10.000 VND** và yêu cầu [nghiên cứu voucher Shopee Việt Nam](../research/2026-10-31-shopee-voucher.md). Đây là đề xuất policy dự án, không phải khẳng định Shopee có mệnh giá giao trễ cố định 10.000 VND. Eligibility, quan hệ nhận voucher hoặc coins/nhận cả hai, và lifecycle vẫn chưa được xác nhận; câu hỏi lựa chọn hoặc chỉ nghiên cứu còn chờ trả lời. Hiệu lực v1 tiếp tục `policy_not_configured`; ghi chú này không thay scope coins + cancel, yêu cầu, schema hay signature đang có.

**Các lựa chọn kỹ thuật đề xuất của tài liệu này:** một state DB mỗi run; freshness business timestamp nghiêm ngặt/global theo feed; sticky proactive control; tick liền nhau 30 phút; decision clock bằng tick cuối đã commit; cancellation chỉ ghi workflow runtime và yêu cầu xác nhận riêng; không TTL tự đặt. Những lựa chọn này chưa phải luật kinh doanh bổ sung. Thiếu căn cứ eligibility vẫn trả review/no grant; không mặc định cho phép khi chưa có policy.

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
5. **R5 — Tick:** A3 → A2 → bàn giao committed output cho A1. Commit heartbeat/health/control/incidents/assessment/questions/progress/checkpoint cùng transaction; retry không nhân progress hay output. Chưa có A1 seam thật thì pipeline toàn phần được báo pending.
6. **R6 — Authority:** Action là request; source/role/ownership từ server wiring và session đã xác thực. Không deserialize context từ body; A2/A3/LLM không được ghi tiền. Chỉ public `platform_huy.execute_action` ghi ledger xu.
7. **R7 — Coins:** explicit customer text trong chat A1 đã mở; đúng order/customer; late_days >=2 ngày lịch VN; bằng chứng xác định không lỗi khách, không bất khả kháng; lịch sử đủ kiểm once/order; amount server tính lại. Unknown/mâu thuẫn/stale facts hoặc thiếu policy → blocked/review, không grant.
8. **R8 — Atomicity:** cùng key/cùng semantic request trả persisted result; cùng key/khác payload hoặc principal → conflict. Tối đa một ledger xu/order trong một state authority. Coins chỉ là runtime ledger effect; không nói đã chuyển tiền hay xu tới hệ thống ngoài.
9. **R9 — Cancel:** bước đầu không hủy; xác nhận lần hai bind request/order/customer/version; sau đó vào review runtime. Approval không UPDATE nguồn, không chứng minh carrier đã hủy, không tự hoàn tiền. Client queue/needs_approval không bypass.
10. **R10 — Return signal:** chỉ seller của order đang xem, customer suy từ order; đếm request và DISTINCT order riêng; physical returned scan riêng. Lọc as-of, ghi window/coverage/provenance, không lộ shop khác/PII; không thay fault/coins eligibility.
11. **R11 — Verification:** literal expected từ luật trước code; kiểm output và SQL state thật, crash/concurrency; giữ test người khác. Suite xanh không được dùng làm chứng nhận A1/provider chưa tích hợp.

| Module/file dự kiến | Trách nhiệm / owner |
| --- | --- |
| `platform_huy/sources.py`, `validation.py`, `replay.py` | Read-only source identity, projection bổ sung, validator, ingestion watermark — Huy |
| `platform_huy/state.py`, `tick.py`, `guard.py` | Migration, checkpoint, A2 adapter, heartbeat/control/gate — Huy |
| `platform_huy/execution.py`, `cancellation.py`, `return_history.py` | Permission, evidence, ledger, cancel workflow, authorized counts — Huy |
| `platform_huy/__init__.py`, `contracts/platform.py`, `contracts/__init__.py` | Public export và additive types; giữ constructor Action/OrderAssessment v0 — Huy |
| `contracts/migrations/001_platform.sql`, `platform_huy/tests/test_*.py`, `pytest.ini` | Companion state, unit/integration module tests, thêm collection — Huy |
| `acceptance_truc/` | Huy viết acceptance cho A1 thật khi Trúc bàn giao seam; hiện pending |
| `logistics_an_nguyen/`, `acceptance_huy/`, `acceptance_an_nguyen/` | Chỉ đọc; không sửa code A2/test owner khác |
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

**Decision clock:** `simulated_now = replay_checkpoint.tick_at` mới nhất đã commit của active run; start_at chỉ ấn định tick đầu, không cấp quyền trước tick đó. Mọi business mutation trước tick đầu raise `run_not_ready` và không ghi; gate trả false với `run_not_ready`. Chỉ bootstrap/migration và run_tick được chạy để đưa run sẵn sàng. Giữa hai ticks đồng hồ đứng yên: sau tick10:00, wall clock10:17 vẫn quyết định tại10:00; chỉ commit tick10:30 mới chuyển now sang10:30. Restart đọc checkpoint đó, không dùng process uptime/wall clock hoặc start_at ghi đè thời gian. Re-read clock/version trong transaction mutation; nếu checkpoint đã đổi từ lúc chuẩn bị facts thì rebuild/revalidate theo now mới trước khi ghi, không commit facts cũ.

Caller timestamps là event/audit hoặc historical query, không là evaluation clock: Action.requested_at, opened_at, message.created_at và control.at phải aware và <=now; future → validation_error. Quá khứ được lưu audit nhưng proactive gate/control release luôn đánh giá tại now, không tại opened_at/at. Evidence.prepare.as_of bắt buộc ==now, khác → validation_error; chỉ return-history đọc lịch sử mới cho coverage_start<=as_of<=now. Trước tick đầu các read cần current authorization/gate cũng trả run_not_ready. Không wall-clock business logic hoặc TTL mới.

Một run nhận start_at explicit, sau đó chỉ T+30 phút. Nếu T có tick_results đã commit thì trả bản đã lưu trước mọi kiểm sequencing, kể cả retry tick cũ; đây là đọc lại, không rewind state. T chưa commit mà nhỏ hơn checkpoint hoặc không đúng tick tiếp theo trả `tick_sequence_invalid`; chọn run mới để thực sự rewind. Delta query `previous_watermark < ingested_at <=T ORDER BY ingested_at,event_id`, đọc trọn nhóm trước watermark. Full cumulative snapshot cùng cutoff đi vào A2, delta không thay full snapshot.

Mỗi attempt Huy kiểm trực tiếp mọi raw scan có ingested_at<=T trước khi dùng A2 reader; query A2 có event_at<=T không được che scan corrupt. Huy kiểm join order visible, quarantine/mask xong mới đưa projection an toàn cho adapter. Tạo ProgressTracker mới từ state committed → `ReleaseAdapter(snapshot).orders()` → `tracker.apply(..., tick_at=T, feed_health=health)` → `evaluate_tick(...)`. Dùng đúng `OrderFacts.required_feeds` và `FeedHealth` hiện có. `QuestionStore.save` dùng transaction state; serialized progress lấy adapter Huy round-trip đúng `tracker.records`, không sửa A2. Không dùng A2 CLI/progress.json làm coordinator. Projection dict là bản riêng cho attempt, không hứa frozen sâu.

Sau compute, `BEGIN IMMEDIATE`, so lại checkpoint.version; thay đổi thì bỏ attempt/reload. Ghi mọi tick row và checkpoint.version+1 rồi COMMIT; chỉ sau đó API/A1 đọc tick mới. Exception → ROLLBACK và bỏ tracker tạm. Busy timeout=5 giây, trả `state_busy` để caller retry toàn attempt; không loop vô hạn. Export JSON sau commit từ state, không trở thành authority thứ hai.

Checkpoint nghĩa A3+A2 cùng ingestion watermark/progress đã durable, **không nghĩa A1/contact đã chạy**. tick_results là durable handoff với a1_status=pending_integration. Khi Trúc nối consumer, khóa handoff ổn định `(run_id,tick_at,order_id)` dùng cho contact/action idempotency; reread tick không tự sinh Action. Không gọi A1 hoặc external delivery trong SQLite transaction và không dùng no-op A1 làm success.

Control duy nhất bản đầu `proactive_contact_allowed`, scope=`global`, bool. Khởi tạo true không vượt gate nguồn; A3 được true→false/false→false, false→true trả `control_relaxation_denied`. Feed hồi phục có thể trusted nhưng control vẫn false. Human có capability `controls:release` mới mở lại; trong transaction kiểm source/heartbeat hiện tại bằng cùng gate bỏ riêng sticky false, audit incident, rồi mở. Không mở từ source text/LLM. Không tạo control tiền mới.

`can_proactively_contact(order_id)` tự resolve OrderFacts/assessment và required_feeds từ committed snapshot đúng run; caller không truyền facts hay rút ngắn feed dependencies. Đọc heartbeat A3 và health mới nhất <=now, assessment <=now, toàn required feeds usable_at(now), control true. Gọi lại ngay trước thực sự mở/gửi proactive; tick permission không phải send permission. Historical query không thể authorize current contact. Không có transport nên Huy cung cấp gate; Trúc chịu việc nối gate với thao tác contact thật. Gate proactive không cấm mặc định inbound/cancel/review.

## 4. Giao diện Python đề xuất

Types sau là additive, frozen dataclasses trong `contracts/platform.py`; tuple bất biến ở ranh giới. Shared DTOs chỉ import stdlib và contracts.types, **không runtime-import logistics_an_nguyen hoặc platform_huy**; contracts.__init__ chỉ export các DTO độc lập. Platform class và wiring functions nằm platform_huy. FeedHealthRecord là DTO wire/state riêng; adapter Huy map 1:1 các trường sang đúng A2 FeedHealth nội bộ khi gọi A2, không đổi A2 enum/model/usable_at. Điều này tránh vòng import khi A2.models import contracts rồi contracts export platform types. Các JSON string phải canonical JSON (sort_keys, UTF-8, không NaN) với schema mô tả tại mục 5. Các signature là thiết kế, chưa phải code tồn tại.

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
class ExecutionResult:
    action_id: str
    decision: Literal["succeeded", "blocked"]
    reason_codes: tuple[str, ...]
    amount_xu: int | None
    ledger_id: str | None
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
    def run_tick(self, *, tick_at: datetime) -> StoredTick: ...
    def can_proactively_contact(self, order_id: str, *,
                                context: ServerContext) -> GateDecision: ...
    def set_proactive_control(self, allowed: bool, *, at: datetime,
                              context: ServerContext, reason: str) -> GateDecision: ...
    def record_contact_opened(self, *, contact_id: str, order_id: str,
                              channel: Literal["chat", "web_voice"], proactive: bool,
                              opened_at: datetime, context: ServerContext) -> None: ...
    def record_customer_message(self, *, message_id: str, contact_id: str,
                                body: str, origin: Literal["text", "voice_transcript"],
                                created_at: datetime, context: ServerContext) -> str: ...
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

`bind_platform` chỉ server startup dùng một lần để bind active run; rebinding khác run đang active trả validation_error. Module export `platform_huy.execute_action` delegate đúng Platform đó; chưa bind trả validation_error, client không chọn DB/run. `ServerContext` được trusted adapters tạo; capability tối thiểu: `actions:coins`/`cancel:request`/`cancel:confirm`/`cancel:read`/`cancel:review`/`actions:read`/`returns:read`/`contacts:write`/`controls:tighten`/`controls:release`. Kiểm cả capability, source, customer/seller ownership. Context construction đơn thuần không là sandbox bảo vệ trước malicious Python module có quyền DB.

Validation/permission/not-found/conflict/storage errors raise PlatformError với code ổn định: `validation_error`, `permission_denied`, `not_found`, `idempotency_conflict`, `version_conflict`, `state_busy`, `source_invalid`, `tick_sequence_invalid`, `run_not_ready`. Unauthorized order trả `not_found` để không lộ tồn tại. Gate denial là GateDecision false; request đúng shape/authority nhưng không đủ business facts trả ExecutionResult blocked và receipt. Trúc map ra HTTP; Huy không quyết route/auth framework. Không catch rộng rồi trả success.

## 5. State và tương thích migration

Giữ nguyên tám bảng v0 và CHECK/FK/UNIQUE hiện có; không thêm trigger khiến fixture INSERT v0 của acceptance_huy hỏng. Production services thực thi invariant bổ sung. `schema_state.sql` vẫn bootstrap v0, migration 001 chạy trước business transaction; không `executescript` giữa tick/action. Chỉ một state DB/run, không đổi PK heartbeat/health hiện có.

Trong bảng schema dưới đây, trường không ghi kiểu là TEXT; singleton/version là INTEGER, JSON/hash/timestamp lưu TEXT; nullable chỉ những trường ghi nullable. Khóa/FK và enum được migration thực thi; service kiểm cross-row order/customer relationships.

| Bảng bổ sung | Schema bắt buộc (mọi ID/key NOT NULL, JSON CHECK json_valid) |
| --- | --- |
| schema_migrations | version INTEGER PRIMARY KEY, applied_at TEXT |
| run_metadata | singleton INTEGER PK CHECK=1, run_id UNIQUE, source_identity_json, start_at, policy_version=`huy-v1` |
| replay_checkpoint | singleton INTEGER PK CHECK=1, tick_at nullable, scan_watermark nullable, version INTEGER >=0 |
| tick_results | tick_at PK, result_json, result_sha256; result có assessments/health/quarantined IDs/A1 pending và required_feeds_by_order từ OrderFacts committed |
| a2_progress | singleton INTEGER PK CHECK=1, tick_at, records_json; canonical round-trip tracker.records |
| customer_messages | message_id PK, contact_id FK contact_log, order_id, customer_id, origin enum text/voice_transcript, created_at, body, request_code nullable late_compensation, request_rule_version nullable, recorded_by |
| execution_evidence | evidence_id PK, order_id, contact_id FK nullable, message_id FK nullable, assessment_at, visible_at, policy_version, payload_json, sha256, created_by |
| action_receipts | action_id PK FK outbox, request_hash, principal_id, attested_source, evidence_id FK nullable, decision_code, result_json, decided_at |
| cancel_requests | cancel_id PK, request_action_id UNIQUE FK outbox, order_id, customer_id, status CHECK CancelStatus, confirmation_id UNIQUE, version>=1, order_snapshot_sha256, requested_at, confirmed_at nullable, reviewed_at/by/reason nullable |
| workflow_commands | idempotency_key PK, request_hash, principal_id, cancel_id FK, result_json, created_at; confirm/review durable retries |

Migration kiểm version; v0 →001 transactional, chạy lại no-op; version cao hơn hỗ trợ trả source/state error và không ghi. State cũ thiếu metadata chỉ adopt khi tám bảng v0 rỗng; state đã có dữ liệu nhưng không xác định source/run trả `source_invalid`, yêu cầu run mới, không backfill provenance giả. Kết nối mới luôn `PRAGMA foreign_keys=ON`. Không migration source DB. Không tạo financial_effects/delivery_outbox khi chưa có policy/provider.

Evidence payload gồm source identity/as_of, order/customer/seller, items_value, assessment snapshot/hash, contact/message provenance, `fault_verification=verified|unknown|conflicting`, `force_majeure=present|absent|unknown`, `force_majeure_evidence_refs`, visible historical ledger refs và `history_classification=clear|already_granted|ambiguous|unavailable`. Immutable qua service; hash nhận diện payload, không cấp authority.

**Explicit request seam:** trusted server startup truyền `request_rule` là adapter deterministic/versioned thuộc A1 của Trúc; không deserialize callback/version từ HTTP, không dùng LLM verdict, không tự thêm keyword matcher thay A1. `record_customer_message` với contacts:write xác minh authenticated customer và contact/order/origin; origin lấy từ trusted transport event (typed customer text hoặc voice transcript), không từ client claim. Service lưu body gốc rồi gọi rule.recognizes(body) chỉ khi origin=text và contact A1-opened chat. True mới mint request_code=late_compensation và request_rule_version; False/không adapter để cả hai null. Adapter error abort transaction với source_invalid, không mint signal. Client/A1 output JSON không có quyền gửi request_code; evidence builder chỉ resolve giá trị do service đã mint. Thiếu signal → blocked invalid_request_provenance. Đây là API nối rule thật, không khẳng định A1 đã có; tests fixture rule chỉ ở test construction, không client-accessible attestation endpoint.

`record_contact_opened` cần contacts:write và ownership; proactive=true bắt buộc source=a1 và kiểm gate tại server now, initiated_by=A1 do server gán; inbound source app gán customer. opened_at chỉ event audit <=now. Cùng contact_id/cùng facts no-op, khác facts conflict; record message tương tự immutable bằng ID. Ghi contact không giả external provider đã mở; adapter chỉ gọi sau event mở phiên thật. Evidence builder tự resolve latest committed assessment và nguồn tại now (as_of phải bằng now), không nhận eligibility facts từ khách; mặc định FM unknown như mục 6.

prepare_execution_evidence không contact/message chỉ tạo order-authorized snapshot cho cancel_request từ customer/app/A1 có cancel:request; không có request signal nên không thể cấp coins. Khi truyền contact/message phải truyền cả hai và service kiểm bindings; coins luôn cần provenance đầy đủ. Gate đọc required_feeds_by_order đã commit, không lấy dependency list từ API input.

## 6. Executor coins và cancellation

Executor resolve evidence và source identity/as_of server-side; so message.order/contact.order/evidence.order/action.order và customer. Message phải nằm sau opened_at, trước closed_at nếu có, không future; contact A1-opened channel chat. `origin=voice_transcript` không được text request. Không tự đặt TTL phiên; closed session có message hợp lệ vẫn được kiểm theo facts tại decision, không phải miễn kiểm freshness.

Evidence phải thuộc latest committed assessment của order, không future; executor kiểm lại required FeedHealth.usable_at(simulated_now) và visible source facts, không dùng historical health boolean để chứng minh tài chính hiện tại. Không áp heartbeat proactive thành lệnh cấm mọi money request; thiếu current financial evidence riêng vẫn fail closed.

Coins dùng `late_xu_for` hiện có nhưng independently kiểm quote; int chính xác, không bool/float/âm. Action.amount_vnd với kind coins mang số xu vì compatibility, ledger.amount_xu là unit thật; không đặt tỷ giá. Late_days giữ cách A2: max(0, date_VN(delivered_at hoặc T) − guaranteed_date), không đổi sang 48h. Guaranteed 29/10, T=31/10 00:00 VN →2. Không ép status chỉ `late`: fault/FM/health/facts phải đủ, exception không tự được cấp hoặc tự bị loại bằng luật chưa duyệt.

Source lịch sử có visible coins/late-compensation được policy nhận diện → `already_granted`; non-coins voucher/refund/hoàn ship không tự quy thành coins, nhưng mapping chưa rõ → `history_policy_unknown` review/no grant. Không history read → `history_unavailable`. Future ledger không ảnh hưởng hiện tại. **Chưa có classifier/rule chứng minh FM absent trong repo:** mặc định unknown → `force_majeure_unknown`; không dùng “không thấy cảnh báo” hoặc carrier/platform fault để tự cho absent. V1 cung cấp gate và tests với verified fixtures; release-wide coins enablement còn bị chặn cho đến khi có rule/evidence được Huy duyệt. Không phát minh classifier trong implementation plan.

Canonical semantic hash gồm principal/source/order/kind/amount/evidence_ref/confirmation_id. Exclude action_id, requested_at, queue, needs_approval; requested_at phải aware, <=simulated now và chỉ audit, không chọn as-of; queue/approval server quyết. Cùng key retry trả action_id/result cũ dù caller tạo action_id mới. Queue=`local_coins`/`cancel_review`/`local_notice`, không external broker. eta_notice chỉ ghi local intent, không gọi gửi và không claim delivered; proactive notice phải qua gate khi Trúc nối transport.

Same action_id với key mới conflict; legacy outbox trùng key nhưng không có trusted receipt trả blocked `legacy_unverified`, không suy success từ SQL status. Request blocked được lưu cùng key; đổi facts cần key mới. `workflow_commands` và outbox đều dùng namespace key toàn run: collision cross-table được service kiểm trong transaction, không né conflict bằng đổi entry point.

Coins transaction `BEGIN IMMEDIATE`: kiểm key/hash → recheck controls/facts/history/local ledger → INSERT outbox + receipt; blocked → outbox blocked; đủ điều kiện → ledger_new + outbox succeeded + receipt; COMMIT. Response `succeeded` nghĩa local ledger committed. Before-commit crash rollback tất cả; after-commit/lost-response retry đọc receipt. Different key same order → blocked `already_granted`; race serialize trong cùng DB. Grant ở hai run DB/reset runs không có bảo đảm once/order chung; đây là replay isolation, không production wallet.

Voucher/refund/shipping_fee_refund với authority hợp lệ luôn blocked `policy_not_configured`, không ledger; source sai bị permission_denied trước. A3 không có money capability. Không dùng control proactive như blanket ban inbound/cancellation, nhưng financial evidence stale/conflicting vẫn blocked `financial_evidence_untrusted`.

Cancellation dùng hai lượt/API calls riêng: request → awaiting_confirmation (version=1, confirmation_id random mới); confirm đúng principal/customer/order/id/version → awaiting_review (version=2); reviewer có `cancel:review`, reason không rỗng → approved/rejected (version=3). Request Action amount=0, queue/needs_approval do gate ấn định. `execute_action(cancel_request)` với evidence order-authorized mở cùng workflow, không tự consume confirmation; dedicated methods gọi cùng private persistence. ExecutionResult.cancel_id chứa ID workflow durable; kind khác hoặc cancel bị blocked thì null.

`list_order_actions` và retry execute_action trả immutable receipt của request ban đầu, gồm cancel_id, không giả nó là current workflow. `get_cancellation(cancel_id)` trả current CancellationResult gồm confirmation_id/version/status, cho customer có cancel:read đúng customer của order hoặc A1 server được delegate cho customer đó; reviewer dùng cancel:review riêng. Customer không cần và không được vào list_review_queue. Lost response/restart: retry Action cùng key lấy action/result/cancel_id cũ, hoặc actions:read own order lấy cancel_id từ history → get_cancellation → confirm → get_cancellation xem awaiting_review/approved/rejected. Không SQL trực tiếp hoặc tạo request mới chỉ để recovery; wrong customer trả not_found. Stable receipt không lộ confirmation cho bên khác.

Confirmation_id là identifier bind state, **không bearer authorization secret**; authenticated customer và version vẫn bắt buộc. Chỉ ID được phát cho request đó mới hợp lệ; first request không đồng thời là confirmation. Adapter Trúc phải bảo đảm separate customer affirmative turn/click, không dùng message khởi tạo làm lần hai. Không expiry thời gian tự đặt; thay đổi visible order snapshot (cancellation/terminal logistics facts) làm `version_conflict`, yêu cầu request mới và confirm lại, không suy carrier cancellation permission. Mỗi command key retry trả persisted result; key đổi payload/principal conflict; confirmation đã consume với key mới trả version_conflict, không review row thứ hai. Reviewer không tự nhập amount; approval không tạo refund. Không claim đơn nguồn hoặc carrier đã hủy.

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
| Crash sau health trước checkpoint; crash sau commit trước response | toàn tick rollback/old progress; retry committed trả stored result không tăng stationary |
| T,T+30,T+60; retry T+30; rewind/skip | apply đúng hai intervals; đọc stored tick; tick_sequence_invalid |
| Trước tick đầu mutation/gate; restart checkpoint10:00; process clock10:17 | run_not_ready/false; now vẫn10:00 và cùng decision, không ledger/contact mới |
| Contact opened_at cũ hoặc control.at cũ khi current feed corrupt; evidence as_of cũ; event timestamp10:17 lúc checkpoint10:00 | current gate false, không authorize; validation_error; validation_error |
| Gate order dependency attempts degraded, caller muốn bỏ attempts | signature chỉ order_id, committed required feeds vẫn giữ attempts; allowed=False |
| Fresh process import contracts rồi A2.models, và ngược lại | cả hai subprocess exit0; shared DTO không runtime-import A2 |
| Coins eligible verified fixture, value239999/None/0/20154000 | một ledger 11000/10000/10000/1000000 tương ứng; unit xu |
| Amount bool/float/âm; action amount sai quote | validation_error hoặc blocked amount_mismatch; ledger delta0 |
| Guaranteed29/10, T31/10 00:00 VN; T30/10 23:59 VN | late_days2 đủ riêng late gate; late_days1 blocked late_days_insufficient |
| App spoof a1; voice transcript; customer-opened chat; other-order message | permission_denied; invalid_request_provenance; invalid_request_provenance; evidence_binding_invalid; ledger0 |
| A1 request adapter absent/False; client supplied request_code; deterministic adapter True, valid text | persisted request_code null/null; unknown request field rejected by HTTP adapter; only trusted service path mints late_compensation; tiền vẫn qua all gates |
| Customer fault/FM present/FM unknown/history unreadable/voucher mapping unknown | blocked customer_fault/force_majeure/force_majeure_unknown/history_unavailable/history_policy_unknown; ledger0 |
| Same key/same request; same key changed order/amount/evidence/principal | persisted action/result replayed=True, ledger1; idempotency_conflict, không overwrite |
| Two keys one order concurrent; fault giữa ledger/receipt; lost response | một succeeded+một already_granted, ledger1; rollback0 rồi retry1; retry vẫn1 |
| Non-coins authorized; source reviewer tự khai từ app | blocked policy_not_configured ledger0; permission_denied ledger0 |
| Cancel request caller needs_approval=False; valid confirm; approve | awaiting_confirmation/v1; awaiting_review/v2; approved/v3; source DB/ledger không đổi |
| execute_action cancel → lost response/restart → own-key retry/history → get_cancellation → confirm → own getter | cùng cancel_id, v1 rồi v2, current workflow đọc được bằng cancel:read; không reviewer privilege; order/ledger không đổi |
| Wrong customer/order/confirmation; stale version; repeat consumed confirm new key | not_found hoặc version_conflict; version_conflict; version_conflict; không duplicate workflow |
| Two return requests same order + one returned scan; future request | request_count2/order_count1/physical_count1; future không tăng |
| Canceled order/returning/return_failed; final returns refunded before decision visible | physical_count0 cho các status đó; không lộ refund/final status |
| Other seller; missing known-scope link; high count | not_found; unknown_link_count tăng không fake zero; review_required/threshold_policy vẫn None và coins unchanged |

Thực thi bốn subplan theo phụ thuộc: (1) schema+replay/A3/tick và A2 integration; (2) executor/cancel, transaction và provenance seams; (3) return signal; (4) reviewer độc lập và acceptance cross-owner. Unit tests mới ở platform_huy/tests, thêm path vào pytest.ini bên cạnh nguyên ba acceptance folders. Huy không sửa acceptance_huy/acceptance_an_nguyen để làm xanh.

Reviewer sạch nhận spec/public contracts trước implementer narrative, tự lập expected/missing cases; sau đó đọc diff/test/state evidence. Controller chạy negative controls trên bản sao Huy-owned: đổi >30 thành >=30, dùng ingestion thay source age, bỏ once/order, bỏ source binding, đổi voice thành text; test tương ứng phải fail bởi assert nghiệp vụ. Không mutate checkout, source hoặc owner khác; không cài mutation tool/coverage dependency mới. Giữ collected/pass/fail/skip/xfail/exit, không sửa expected theo output sai hay thêm skip để gọi done.

Acceptance hoàn thành phần Huy khi import contracts, unit/integration mới, acceptance hiện có và diff checks thực sự pass; source hashes giữ nguyên; restart/concurrency/idempotency và authorization negative cases có evidence. Báo command/revision/counts/exit và phạm vi chưa thử. Dữ liệu fixture chỉ trong temp/in-memory, không vào release/replay world.

**Chưa được gọi hoàn thành:** acceptance_truc thật còn chờ A1 public seam của Trúc cho intents/rules-before-LLM/validator/handoff/cancel second turn/text-vs-voice và real gateway integration; không tự viết A1 thay owner, mock mất executor hoặc skip rồi báo pass. External provider/voice/HTTP/auth/UI chưa thuộc implementation này. Coins release-wide còn cần FM absent evidence/rule và historical non-coins mapping được duyệt; gate mặc định review/no grant. Approved cancel chỉ là runtime workflow, không carrier cancellation. Đây là các blocker có tên và hành vi fail closed cụ thể, không lời hứa về dữ liệu hay tiền bên ngoài.
