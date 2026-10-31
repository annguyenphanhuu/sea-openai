# Nghiên cứu Huy: kiểm định nguồn, replay và A3

Ngày nghiên cứu: 31/10/2026. Phạm vi là phần Huy, phục vụ đặc tả trước khi lập kế hoạch và triển khai. Đây là đề xuất có nêu các quyết định còn thiếu, không phải xác nhận pipeline đã chạy hoặc tự bổ sung luật nghiệp vụ.

Đã đọc `AGENTS.md` cấp workspace/repository, `docs/team_plan.md`, `docs/decisions.md`, `docs/data_audit.md`, contracts và các lớp A2 hiện có. Đã đọc Superpowers `using-superpowers` và Codex adaptation; skill ghi rõ subagent được giao việc cụ thể bỏ qua workflow tổng quát đó. Không tạo agent con. Chỉ đọc hai SQLite release bằng URI `mode=ro`, đặt `query_only=ON`; không đọc truth/heldout, không sửa source hay chạy lại hash toàn file. Số liệu audit cũ được ghi rõ là kế thừa, không coi là phép đo mới.

## 1. Kết quả thực tế và ranh giới sở hữu

`platform_huy/` mới có README và prototype UI thuộc Trúc. Chưa có source validator, ops reader, A3, gate chủ động liên hệ, tick transaction hoặc replay checkpoint. `contracts/schema_state.sql` có tám bảng nhưng chưa có bảng run/checkpoint/progress/assessment snapshot. Không có implementation executor trong phạm vi nghiên cứu này.

A2 có sẵn các giao diện cần giữ:

```python
ReleaseReader(core_path: Path | str)
ReleaseReader.snapshot(tick_at: datetime) -> ReplaySnapshot
ReplaySnapshot(tick_at, orders, scans, attempts, reports)
ReleaseAdapter(snapshot: ReplaySnapshot).orders() -> tuple[OrderFacts, ...]
FeedHealth(feed, status, checked_at, source_timestamp=None, last_ingested_at=None)
ProgressTracker(records: dict | None = None)
ProgressTracker.apply(orders, *, tick_at, feed_health) -> tuple[OrderFacts, ...]
evaluate_tick(orders, *, tick_at, feed_health) -> TickResult
QuestionStore(connection).save(questions) -> None
assessment_payload(assessment) -> dict
```

- `REQUIRED_FEEDS = ("orders", "scan_events", "delivery_attempts")` trong A2 adapter. `linehaul_reports` hiện là text không có cấu trúc, không tự thành dependency structured. Nếu adapter sau này thêm feed structured, A2 tự kiểm thêm feed đó.
- `FeedHealth.usable_at(tick_at)` yêu cầu status trusted, source timestamp có thật, `source_timestamp <= checked_at <= tick_at`, tuổi nguồn không quá 30 phút, ingestion nếu có không vượt tick. `checked_at` mới không cứu được nguồn cũ.
- `evaluate_tick` cần snapshot tích lũy đầy đủ, không nhận riêng delta; có đúng một `OrderFacts` mỗi đơn, output sắp theo ID. Đây là hàm đánh giá thuần; không kiểm heartbeat, không gửi contact hay ghi tài chính.
- `ProgressTracker.apply` thay `tracker.records` trong bộ nhớ. Retry cùng tick không tăng stationary count; tiến đúng 30 phút mới tính interval; rewind bị từ chối. Controller phải khởi tạo lại tracker từ state đã commit sau lỗi, không tái dùng instance đã chạy dở.
- `QuestionStore` không commit, không tạo schema; chấp nhận state trong `runs/` hoặc memory. Có thể dùng trong transaction do Huy quản lý.
- A2 CLI hiện ghi JSONL, summary và `progress.json` riêng. Rename progress file chỉ bảo vệ file đó; không tạo tính nguyên tử giữa A3, output và checkpoint. Không dùng CLI này làm transaction coordinator.
- `ReplaySnapshot` là frozen dataclass nhưng chứa các dict mutable. Không gọi nó là snapshot bất biến sâu. Huy có thể tạo bản sao projection cho mỗi consumer/attempt, chỉ lưu bản JSON canonical đã commit; nếu cần đổi kiểu A2, phải yêu cầu An Nguyen sửa. Python cũng chỉ mô phỏng frozen ở mức attribute, không tự đóng băng object con. [Python dataclasses](https://docs.python.org/3.11/library/dataclasses.html#frozen-instances)

Phần Huy không sửa thuật toán ETA, dedup, fault hay progress trong `logistics_an_nguyen/`. Huy cung cấp validated snapshots, health và transaction cho các API có sẵn; nhờ An sửa nếu integration test phát hiện lỗi trong phần A2. Trúc tiếp tục sở hữu HTTP/auth/UI và A1.

## 2. Schema nguồn và ánh xạ thời gian

Đã đọc trực tiếp schema, view và index của hai release DB. Scan có `ix_scan_ingested(ingested_at)` và `ix_scan_order_ing(order_id, ingested_at)`; không cần thêm index vào source. Ops metrics dùng khóa chính `(ts, service_id, metric)`. Không bảng nào ngoài scan có `ingested_at`.

| Nguồn | ID ổn định | Khả năng thấy tại tick T | Timestamp nguồn/freshness | Trường phải che hoặc giới hạn |
| --- | --- | --- | --- | --- |
| `orders` | `order_id` | `created_at <= T` | `created_at` cho mapping tối thiểu | `cancelled_at`, `cancel_actor`, `cancel_reason` chỉ hiện khi cancelled_at <= T; không dùng estimated_date thay guaranteed_date |
| `shipments` | `shipment_id` | `created_at <= T` | `created_at` | Chỉ join đơn nhìn thấy |
| `scan_events` | `event_id` | `ingested_at <= T`; validate event_at <= ingested_at | `event_at`, tách `ingested_at` | Cursor D5 vẫn là ingestion; sau lọc mới sắp tiến trình bằng event_at |
| `delivery_attempts` | `attempt_id` | `attempt_at <= T` | `attempt_at` | Không có bằng chứng timestamp nhận riêng; gọi là availability quy ước, không giả là ingestion đo được |
| `linehaul_reports` | `report_id` | `reported_at <= T` | `reported_at` | Driver note/reason vẫn là text chưa xác minh |
| `linehaul_trips` | `trip_id` | Chưa có timestamp tạo/nhận; view nguồn hiện cho tất cả planned trips | Không có freshness/availability đáng tin cho cả row | Che depart_actual_at, arrive_actual_at theo từng mốc; loaded_parcels chỉ sau departure; status suy từ mốc đã thấy. Tạm không đưa planned trips vào slice A2 đầu tiên vì chưa chứng minh lịch được biết từ lúc nào |
| `returns` | `return_id` | `requested_at <= T` | `requested_at`; quyết định tại `decided_at` | Trước decided_at: status=requested, decided_at/refund_vnd=null |
| `compensation_ledger` | `entry_id` | `created_at <= T` | `created_at` | Chỉ đọc lịch sử; audit cũ có 1.115/2.701 order_id ngoài lát, không coi là toàn DB hỏng |
| `tickets` | `ticket_id` | `created_at <= T` | `created_at` | Không có order_id riêng/cờ A1 mở; không dùng làm bằng chứng xin xu hợp lệ |
| `external_events`, `inventory_events` | `event_id` | `ts <= T` | `ts` | Không tự suy force majeure từ text hoặc chỉ có một cảnh báo |
| `inventory_snapshots` | date/warehouse/product | Theo view nguồn: ngày snapshot lúc 00:00 +07 | Chỉ có ngày | Đây là quy ước view, chưa chứng minh thời điểm publish; không cần cho slice đầu |
| ops `metrics` | `(ts, service_id, metric)` | `ts <= T` | `ts`, đúng service/metric | Value phải hữu hạn; không lấy mẫu tương lai hay MAX từ service khác |
| ops `logs`, `alerts`, `deploy_events` | log_id/alert_id/deploy_id | `ts <= T` | `ts` | Parse JSON có giới hạn; text là dữ liệu, không thi hành runbook/log instruction |
| ops `webhook_inbox` | `msg_id` | `received_at <= T` | Chỉ có `received_at`; không có carrier event_at | `processed_at` chỉ hiện khi <= T; nhận webhook không chứng minh scan nguồn tươi |

Các bảng tham chiếu không có lịch sử version không được tự coi là bảng sự kiện. Slice đầu chỉ lấy allowlist cột đã cần; không đưa toàn DB hoặc raw connection cho agent. Nếu dùng customer/seller metadata thì cần lọc created_at khi có, và không coi giá hiện tại của sản phẩm là giá lịch sử; order_items.unit_price_vnd là trường lịch sử riêng.

Source `v_*_asof` đều phụ thuộc `sim_clock`, không dùng trực tiếp cho tick tùy ý và không UPDATE sim_clock. A2 reader hiện đã truy vấn tham số cho bốn bảng, mask cancelled_at, lọc scan theo ingestion lẫn event time. Nó chưa đọc các cột cancel_actor/reason nên chưa lộ chúng; khi mở rộng projection phải mask cả nhóm. Immutable file chỉ ngăn thay byte, không làm các cột kết cục tương lai an toàn ở tick quá khứ.

Với dữ liệu đã kiểm là ISO giây đồng nhất +07:00, cutoff hiện đổi cùng offset trước khi so TEXT. Validator phải xác nhận invariant định dạng/offset trước khi dựa vào thứ tự từ điển; dữ liệu nhiều offset cần parse thành instant hoặc projection canonical riêng. Không dùng wall clock máy 31/10 để stale snapshot 28/10. Datetime phải aware; state/wire chuẩn hóa UTC microseconds Z như contract. [Python datetime](https://docs.python.org/3.11/library/datetime.html#aware-and-naive-objects)

## 3. Kiểm định: lỗi file, lỗi tương lai và lỗi snapshot

Đề xuất ba cấp, tránh đem thông tin tương lai vào health hiện tại:

1. **Khởi động:** file tồn tại, đúng đường dẫn release được phép, mở read-only, schema/cột/PK cần thiết, manifest identity, quick_check; có thể kiểm định dạng timestamp một lần và cache kết quả theo source identity. File/schema hỏng hoặc identity không khớp thì không bắt đầu run. Đây là lỗi toàn nguồn, không suy ra lỗi một đơn. Không chạy hash/quick_check mỗi tick.
2. **Catalog validation ngoài luồng agent:** phát hiện lỗi semantic ở toàn file có thể ghi vào audit kín, nhưng lỗi có availability hợp lệ sau T không tự làm health tại T corrupt. Đến tick lỗi đó nhìn thấy mới quarantine/report. Nếu timestamp quyết định availability bị malformed, không thể chứng minh row thuộc tương lai: từ chối nguồn/nguồn feed vì không xác lập được as-of, không âm thầm bỏ row.
3. **Snapshot tại T:** validate kiểu, timestamp aware, liên kết giữa các row nhìn thấy và các trường đã mask. Scan có event_at > ingested_at là corrupt input, không chỉ loại khỏi query rồi báo trusted. Row chưa ingest thì không cho A2 nhìn thấy; join với future order/shipment phải bị chặn. Một lỗi visible không được bị MAX(timestamp hợp lệ khác) che đi. Feed affected corrupt và proactive fail closed; phạm vi quarantine chi tiết phải được chốt, không tự sửa row. Order thiếu/sai guaranteed_date phải quarantine hoặc báo lỗi trước ReleaseAdapter (hiện gọi date.fromisoformat trực tiếp); không điền ETA/ngày giả. Tiny có toàn bộ guaranteed_date null theo audit cũ nên phải thể hiện nhánh thiếu dữ liệu này.

`quick_check` kiểm cấu trúc nhanh nhưng không thay các kiểm tra semantic/quan hệ. `foreign_key_check` chỉ xét quan hệ đã khai báo trong DB; những join nghiệp vụ cần truy vấn riêng. Không bật FK rồi tuyên bố lịch sử ngoài lát là corrupt nếu schema không buộc hoặc audit đã ghi nhận giới hạn đó. [SQLite PRAGMA](https://www.sqlite.org/pragma.html#pragma_quick_check), [foreign_key_check](https://www.sqlite.org/pragma.html#pragma_foreign_key_check)

Mở source qua `Path.resolve(strict=True).as_uri() + "?mode=ro"`, `uri=True`, thêm query_only và đóng connection đúng vòng đời. Giữ state ở connection khác dưới `runs/`; không ATTACH state writable vào source reader. Không cần `immutable=1`: nó tắt locking/change detection khi SQLite tin file bất biến, nên không thay thế chính sách read-only hay hash. [SQLite URI filenames](https://sqlite.org/uri.html)

Audit cũ đã có SHA-256 khớp manifest. Đề xuất kiểm một lần lúc tạo run nếu identity chưa được xác nhận cho lần chạy đó, lưu identity; kiểm sau chuỗi integration khi cần chứng minh bất biến. Stat/mtime chỉ là dấu hiệu thay đổi, không chứng minh content không đổi. Có thể dùng standard library `hashlib.file_digest` trên Python 3.11. [Python hashlib](https://docs.python.org/3.11/library/hashlib.html#file-hashing)

## 4. Ba phương án feed health và khuyến nghị cho hackathon

Tài liệu repo chốt ngưỡng D3 nhưng chưa chốt logical feed → service heartbeat, ngưỡng lag/error hay kỳ vọng sparse business events. Ops thực có tám service; description xác nhận order-service tạo đơn, tracking-ingest nhập scan, carrier-gateway nhận webhook, kafka-tracking là Kafka. Không có service được ghi rõ riêng cho delivery_attempts. Metrics có 46 cặp service/metric, mỗi cặp 6.336 mẫu trong toàn release; carrier-gateway có carrier_api_timeout_rate, tracking-ingest/kafka có queue_oldest_age_s. Đây là quan sát schema/data, chưa phải permission policy.

| Phương án | Timestamp health | Điểm mạnh | Giới hạn/quyết định |
| --- | --- | --- | --- |
| A. Mapping event nghiêm ngặt | orders→created_at; scan_events→event_at của scan đã ingest; delivery_attempts→attempt_at | Giữ tên A2, đúng nguồn thực, thư viện chuẩn, không bịa heartbeat | Feed sparse có thể stale cả khi hệ thống hoạt động; cấp quyền liên hệ sẽ bảo thủ, đặc biệt ban đêm |
| B. Liveness bằng telemetry | metric.ts của service đã duyệt cho từng feed, source event age lưu riêng | Phân biệt ít sự kiện với outage tốt hơn | Cần quyết định rõ D3 cho phép source_timestamp của logical business feed là heartbeat telemetry; mapping attempts còn thiếu; telemetry mới không chứng minh backlog không mất dữ liệu |
| C. Registry theo feed/carrier/service và checkpoint mọi stream | Identity rõ, timeline availability, liveness và lag tách riêng | Chi tiết khi một carrier hỏng và carrier khác bình thường | Mở rộng hợp đồng scope health/A2, nhiều policy và test; không phù hợp tự thêm trong 7 giờ |

**Khuyến nghị slice đầu là A**, kèm ops evidence để giải thích và chờ quyết định B; không tự xây framework C. Mapping A là proposal bảo thủ để đặc tả duyệt, không tuyên bố đã chốt nghiệp vụ. Với A, source_timestamp lấy MAX nguồn hợp lệ trong snapshot đúng logical feed; last_ingested_at của scan lấy MAX ingestion riêng. Với orders/attempts không có ingestion đo được thì để null thay vì nói created_at/attempt_at là thời điểm nhận thực tế. `missing` là không có source row cần thiết/không xác lập được nguồn; `stale` là có timestamp hợp lệ nhưng `T-source_timestamp > 30 phút`; corrupt có incident riêng, không bị nguồn mới hơn che. Thứ tự ưu tiên corrupt/missing khi có nhiều loại lỗi cần chốt; mọi loại đều chặn.

Ví dụ: scan event_at 10:00, ingested_at 11:00, tick 11:00, chỉ có scan này thì age=60 phút và stale. Ingestion 11:00 không làm source_timestamp thành 11:00. Nếu một scan khác trong cùng feed thực sự có event_at 10:50 và đã ingest trước 11:00, cấp feed có thể tươi; scan cũ vẫn là bằng chứng lịch sử của đơn. Không đánh dấu từng đơn stale chỉ vì nó đứng yên. Trong phương án A, feed sparse stale có nghĩa **không đủ điều kiện cấp quyền theo D3 hiện tại**, không đủ bằng chứng kết luận outage hay kiện hàng không di chuyển.

Đối với ops evidence, chỉ dùng scope đã chỉ định: orders có order-service; scan pipeline có tracking-ingest, và carrier-gateway/kafka chỉ là dependency giải thích. Không dùng payment/voucher/notification metric mới để làm orders/scan tươi. `delivery_attempts` chưa có mapping service, nên không nâng trusted từ service bất kỳ. Không tự áp ngưỡng queue_oldest_age_s=1800 hay error_rate bất kỳ thành luật vì repo chưa chốt; cần Huy duyệt nếu muốn B. Không yêu cầu mọi metric/service ops đều tươi mới được liên hệ khi chưa có policy đó. Sau ngày cuối tạo đơn, orders.created_at sẽ cũ dù scan còn chạy đến phần đuôi tháng 11: mapping A lúc đó không đủ để cấp proactive cho các đơn còn lại, cần nói rõ giới hạn này khi chọn demo.

## 5. Global health, gate theo đơn và controls chỉ siết

Schema hiện có khóa health `(feed, tick_at)`, A2 đòi đúng một health mỗi feed; không có carrier/order scope. Vì vậy slice đầu health là global theo logical feed, còn quyền theo đơn được tính từ tập dependency của đơn. Không cho một đơn đã có scan cũ làm global stale, không cho feed không liên quan chặn A2 bằng cách tự thêm vào required feeds. Khi scope hỏng chưa rõ (ví dụ carrier riêng), lựa chọn bảo thủ là block global feed và ghi rõ giới hạn, hoặc xin mở rộng contract; không âm thầm phát minh health per-order.

Guard gửi contact phải kiểm lại ở `send_at` thuộc đồng hồ mô phỏng đang chạy, độc lập với assessment tick: có heartbeat A3 đúng agent/context, `tick_at <= send_at`, tuổi heartbeat <=60 phút, các health cần cho đơn usable tại send_at, control cho phép và assessment không thuộc tương lai. Tại 60 phút vẫn hợp lệ về heartbeat nhưng health có thể đã quá 30 phút nên toàn gate vẫn block. Không chỉ đọc boolean lưu trong heartbeat rồi bỏ kiểm freshness.

`guard_heartbeat` hiện lưu `(tick_at PK, agent_id, recorded_at, proactive_contact_allowed, reason_codes_json)`. Đề xuất tick_at và checked_at là thời gian simulation; recorded_at có thể là wall-clock audit nhưng tuyệt đối không dùng nó thay source time để cho phép. Cần quyết định quy ước recorded_at trước khi API hiển thị. State DB nên riêng cho mỗi run vì schema heartbeat chưa có run_id.

`controls` chỉ có JSON và updated_by CHECK; chưa có khóa/type/order cho mức siết, chưa có runtime auth. Đề xuất tối thiểu một khóa boolean cho proactive contact (tên cần Huy duyệt), thứ tự false chặt hơn true. A3 được true→false và false→false, không false→true, không sửa scope rộng để né control cũ; giá trị không hợp lệ bị từ chối. Chỉ human context đã xác thực mới có quyền nới nếu được giao, sau khi kiểm lại evidence/heartbeat/feed còn tươi tại thời điểm mở. Feed health có thể trở lại trusted như quan sát; sticky control vẫn giữ block đến khi có human mở. Đây là cách diễn giải D3 “A3 chỉ siết” cần xác nhận, không tự thêm retry/budget keys hay policy tiền.

Heartbeat và health của một tick phải commit cùng nhau. Nếu tick A3 thất bại, không ghi heartbeat success riêng. Health khi phục hồi không tự cấp lại quyền vượt controls. A3 không gọi external operations, không thi hành runbook trong source, không tạo ledger.

## 6. Replay/checkpoint và restart tick

Khuyến nghị giữ full as-of snapshot qua A2 reader hiện có; dùng scan delta cursor để kiểm/ghi nhận ingestion tiến lên, chưa xây cache tích lũy mới. Với quy mô audit cũ khoảng 125.827 scan, cần đo một tick trước khi tối ưu; chưa có benchmark trong nghiên cứu này. Snapshot và delta phải dùng cùng cutoff T, cùng source identity.

Cursor là watermark ingested_at của **nhóm timestamp đã đọc hết**. Truy vấn delta `ingested_at > previous_watermark AND ingested_at <= T ORDER BY ingested_at, event_id`; không LIMIT làm chẻ nhóm. Nếu cần paging thì chỉ paging nội bộ, đọc tiếp hết nhóm cuối rồi mới checkpoint. `event_id` chỉ tie-break thứ tự; không đổi D5 thành cursor event_at. Trường hợp 12 dòng cùng timestamp phải thấy đủ dù restart. SQLite có row-value comparison để paging composite nếu sau này cần, nhưng không cần đổi checkpoint contract hiện tại. [SQLite row values](https://www.sqlite.org/rowvalue.html)

Đề xuất bổ sung schema runtime thuộc Huy: metadata version/source identity cho run, một checkpoint tick và scan watermark, A2 progress payload, và output assessment JSON khóa `(tick_at, order_id)`. Dùng một state.sqlite cho mỗi run để tránh sửa PK tất cả bảng hiện có; các bảng mới phải có migration/version rõ ràng. Không dùng file JSON progress bên ngoài làm nguồn chuẩn.

Trình tự một attempt:

1. Đọc checkpoint committed và source identity; từ chối rewind trong cùng run. Retry đúng committed tick trả kết quả đã lưu, không chạy lại progress. Tiến tick mặc định +30 phút; nhảy tick phải được policy chốt, không tự tăng stationary intervals.
2. Đọc source projection tại T, delta trọn nhóm, ops projection tại T. Compute validation/A3 outputs trong bộ nhớ, chưa publish.
3. Tạo `ProgressTracker` mới từ payload đã commit; nối ReleaseAdapter → apply → evaluate_tick. Không chuyển delta trực tiếp cho evaluate_tick, không sửa A2 model/thuật toán.
4. Trên state connection riêng, `BEGIN IMMEDIATE`; đọc lại checkpoint/version để chống hai worker cùng run; nếu thay đổi thì bỏ attempt hoặc retry từ bản mới. Ghi heartbeat, health, incidents, controls siết, assessments, questions, progress và checkpoint trong cùng transaction. Lỗi ở bất cứ bước nào thì rollback toàn bộ, hủy tracker tạm.
5. Sau COMMIT mới cho API/A1 đọc tick mới hoặc xuất JSON từ state. Việc gọi provider ngoài SQLite phải qua outbox/gate và nằm trong slice executor/contact riêng; rollback SQL không thu hồi được một cuộc gọi đã gửi.

Python 3.11 có thể dùng `isolation_level=None` với explicit BEGIN/COMMIT/ROLLBACK; không dùng tham số autocommit mới hơn làm yêu cầu 3.11. Chạy schema/migration trước tick; `executescript` có thể commit transaction đang mở. [Python sqlite3 transaction control](https://docs.python.org/3.11/library/sqlite3.html#transaction-control)

`BEGIN IMMEDIATE` lấy quyền writer ngay, có thể trả busy nếu writer khác hoạt động. Chọn một writer/controller mỗi run, timeout hữu hạn, retry từ checkpoint; không giữ source connection writable. [SQLite transactions](https://www.sqlite.org/lang_transaction.html)

Tính nguyên tử chỉ bao phủ các row trong cùng state transaction; file output ngoài DB và dịch vụ ngoài không nằm trong đó. Các bản JSON xuất lại từ state sau crash không đòi replay thế giới. [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html)

## 7. Giao diện Huy đề xuất, không đổi A2

Các chữ ký dưới đây là contract đề xuất để reviewer đánh giá, chưa là implementation:

```python
class SourceValidator:
    def validate_startup(self, core_path: Path, ops_path: Path) -> SourceIdentity: ...
    def validate_visible(self, snapshot: ReplaySnapshot, *, tick_at: datetime) -> ValidationResult: ...

class OpsReader:
    def snapshot(self, tick_at: datetime) -> OpsSnapshot: ...

class Guard:
    def evaluate(self, snapshot: ReplaySnapshot, ops: OpsSnapshot, *, tick_at: datetime,
                 previous_controls: tuple[Control, ...]) -> GuardResult: ...

def can_proactively_contact(*, order: OrderFacts, send_at: datetime,
                            heartbeat: GuardHeartbeat | None,
                            feed_health: tuple[FeedHealth, ...],
                            controls: tuple[Control, ...]) -> GateDecision: ...

def run_tick(*, tick_at: datetime, sources: ValidatedSources,
             state: sqlite3.Connection) -> StoredTickResult: ...
```

GuardResult chứa health đúng lớp `logistics_an_nguyen.models.FeedHealth`, heartbeat draft, incidents và đề nghị control siết; không tự commit. Không tạo enum feed status riêng khác contract. `can_proactively_contact` trả allowed + reason codes, không gửi contact. Caller server cung cấp context đã xác thực; không lấy actor role từ body LLM/client.

Giới hạn slice đầu: schema/validator + read-only/as-of + tick/state + ba health A2 + heartbeat + control/gate chủ động liên hệ + integration A2. Executor tiền, consent/chat/confirmation, A1 route và provider dispatch được đặc tả/triển khai riêng. Gate proactive này không thay permission executor.

## 8. Kiểm thử biên và quyết định cần chốt

Fixtures trong memory/temp state chỉ kiểm thuật toán, không nhập thêm world data vào replay thật. Huy không sửa acceptance_huy của An; bàn giao các ca này để An viết/kiểm chéo, chạy kiểm tích hợp trong scope Huy được phép.

| Ca | Kỳ vọng chính xác |
| --- | --- |
| Source mở mode=ro, thử UPDATE sim_clock/CREATE INDEX | SQLite từ chối; source hash trước/sau integration khớp, state ghi được riêng |
| Scan event trước T, ingestion T+1 giây | Không thấy tại T, có tại tick đủ điều kiện; không đọc tương lai qua event time |
| 12 scan cùng ingestion, batch/paging nhỏ | Đọc đủ nhóm trước checkpoint; crash giữa nhóm không mất/nhân evidence sau retry |
| Source 10:00, ingestion 11:00, T=11:00 | Scan health stale, last_ingested_at=11:00, source_timestamp=10:00 |
| Source age đúng 30 phút / 30 phút +1 microsecond | Freshness pass / stale; checked_at=T không thay kết quả |
| Source tương lai / checked_at tương lai / ingestion tương lai | FeedHealth không usable; không lấy MAX tương lai |
| Payment metric mới, tracking metric cũ | Không làm scan_events trusted; không dùng MAX toàn metrics |
| Một đơn không có scan mới, feed có nguồn mới hợp lệ | Không coi riêng đơn đó là feed outage; stationary logic vẫn thuộc A2 |
| Attempts yên ban đêm | Theo mapping A có thể stale và block; lý do không ghi “outage confirmed” |
| Malformed row có availability hợp lệ sau T | Không đưa facts/incident semantic đó vào health T; đến khi visible mới xử lý |
| Malformed availability không xác định được trước/sau T | Startup/feed validation fail closed, không silently drop |
| Event_at > ingested_at trong row visible | Corrupt có lý do; query thêm event_at<=T không được che lỗi rồi báo trusted |
| Future cancelled/return decision/trip arrival/webhook processing | Các trường con tương lai bị mask; planned trip chưa có availability không vào slice đầu |
| Heartbeat thiếu / age 60 phút / 60 phút+1 microsecond | Thiếu block; đúng 60 chỉ qua phần heartbeat; quá 60 block; feed gate kiểm độc lập |
| Heartbeat/assessment tương lai hoặc khác run | Không dùng cho phép; state riêng theo run |
| A3 siết true→false rồi feed hồi phục | Control giữ false; A3 false→true bị từ chối; human path riêng có auth |
| Crash sau ghi health nhưng trước progress/checkpoint | Rollback tất cả; retry từ old committed tick cho cùng kết quả |
| Crash sau COMMIT trước xuất JSON | Trả/export kết quả đã lưu; không chạy lại progress, không nhân question |
| Hai controller cùng đọc checkpoint | Một commit; controller còn lại đọc version đổi và retry/return, không ghi đè |
| A2 input ValueError hoặc writer busy | Không heartbeat success/checkpoint một phần; không tái dùng tracker mutated |
| T+30/T+60, retry T+30, rewind T | A2 progress tính đúng 2 interval, retry không tăng, rewind cần run riêng |

Các điểm cần người có quyền quyết định trước khi đặc tả thành final:

1. **Chọn A hay B cho logical feed freshness.** A bám timestamp business source nhưng nhiều tick ban đêm không thể chủ động liên hệ; B cần định nghĩa rõ source_timestamp và mapping service cho delivery_attempts. Không được để ingestion/tick giả làm freshness.
2. **Scope hỏng carrier riêng:** slice đầu global bảo thủ có được chấp nhận hay cần thay contract scope? Hiện A2 chưa nhận health theo carrier/order.
3. **Controls và recovery:** tên khóa proactive, kiểu boolean, human có quyền mở lại, A3 chỉ siết có áp dụng sticky block qua các tick như đề xuất không? Schema JSON tự do chưa đủ quyết điều này.
4. **Clock của recorded_at/gate:** khuyến nghị mọi tuổi nghiệp vụ dựa simulation T; wall clock chỉ audit. Cần ghi rõ cho Trúc để không UI/API dùng nhầm.
5. **Corrupt visible một row:** block toàn logical feed và dừng tick hay commit tick với feed corrupt/quarantine rồi A2 unknown_feed? Cả hai fail closed; cần chọn output/recovery semantics và ưu tiên corrupt/missing khi cùng xảy ra.
6. **Checkpoint contract:** state riêng mỗi run, các bảng mới và migration; tick đầu/start/end/time alignment, có cho nhảy tick không. Không đổi source sim_clock hoặc tự dựa vào wall clock hiện tại.

Các lựa chọn này ảnh hưởng business authorization hoặc hợp đồng chung. Những chi tiết kỹ thuật đã có bằng chứng như mode=ro, parameterized cutoff, tách state, full snapshot cho A2 và atomic checkpoint không cần mở rộng scope sang thuật toán An hoặc API Trúc để thực hiện.
