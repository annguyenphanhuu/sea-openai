# A2 — phần việc của An Nguyen

A2 nhận snapshot đơn hàng, bằng chứng logistics, trạng thái feed từ A3 và thời
gian tick; trả về đúng một `contracts.types.OrderAssessment` cho mỗi đơn cùng
các câu hỏi cần quản lý xác minh. Mã chạy bằng Python 3.11+, chỉ dùng thư viện
chuẩn. Nhãn và feed tuân theo D1–D5 Huy chốt trong `docs/decisions.md` ngày
31/10/2026. Từ vựng adapter, quy lỗi chi tiết và mô hình là phần A2 để team review.

## Phân tích và tình trạng công việc

| Việc An Nguyen phụ trách | Tình trạng |
| --- | --- |
| Phân loại theo thứ tự `STATUSES` | Đã triển khai trong `assessment.py` |
| Tính ngày trễ theo ngày Việt Nam, dừng khi đã giao | Đã triển khai |
| Chọn ETA, fault và risk từ bằng chứng có cấu trúc | Đã triển khai; không tự dựng mô hình dự báo |
| Lọc dữ liệu theo `ingested_at`, kiểm tra dữ liệu đầu vào | Đã triển khai trên snapshot do platform cung cấp |
| Câu hỏi quản lý, lưu/đọc/trả lời và chống trùng khi retry | Đã triển khai trong `service.py` và `questions.py` |
| Đầu ra JSON cho API orders/shop và review | Đã có Python API và serializer để Trúc gắn HTTP route/UI |
| Danh sách ngày đặt/bàn giao cho Trúc | Đã có `assessed_orders_payload` và file `*.orders.json`, kèm bằng chứng as-of và health |
| Kiểm thử biên và lỗi A2 | Đã có trong `acceptance_an_nguyen/` |
| Adapter đọc DB release | Đã nối schema `release_main`, đọc as-of và chỉ đọc |
| Baseline ETA/xác suất | Đã có survival model và CLI kiểm định cửa sổ cố định; chưa hiệu chỉnh hoặc xác nhận chất lượng toàn tập |
| Chạy chuỗi A3 → A2 → A1, HTTP/auth và checkpoint | Huy phụ trách kiểm định/A3/state; Trúc phụ trách A1/UI/HTTP/auth; An bàn giao danh sách assessment |

## Python API

```python
from logistics_an_nguyen import (
    FeedHealth, OrderFacts, QuestionStore, assessment_payload, evaluate_tick,
)

# orders: one OrderFacts per order, accumulated by the platform through this tick.
# health: one FeedHealth per feed, read after A3 runs.
result = evaluate_tick(orders, tick_at=current_tick, feed_health=health)
payloads = [assessment_payload(item) for item in result.assessments]

# runtime_state has already been initialized with contracts/schema_state.sql.
# Platform owns transactions/checkpoints; A2 never commits or initializes schema.
store = QuestionStore(runtime_state)
with runtime_state:
    store.save(result.questions)
open_questions = store.list_questions(status="open", order_id=order_id)

# Call only after the HTTP route has authorized the supervisor.
with runtime_state:
    store.answer(question_id, answer_text=answer, answered_by=supervisor_id,
                 answered_at=current_tick)
```

`assess_order(order, tick_at=..., feed_health=...)` xử lý riêng một đơn.
`evaluate_tick` bỏ qua đơn chưa được ingest, từ chối snapshot trùng `order_id`,
sắp kết quả theo ID và không gây tác động bên ngoài. Không đưa chỉ batch delta
vào hàm này: platform phải hợp nhất lịch sử nhìn thấy thành snapshot đầy đủ.

`OrderFacts` gồm `order_id`, `guaranteed_date` kiểu `date`, `ingested_at` có
timezone, `required_feeds` là tuple tên feed không rỗng, và tuple `Evidence`.
Adapter đáng tin cậy phải liên kết bằng chứng với đúng đơn; contract `Evidence`
không có `order_id`, nên A2 không tự xác minh được liên kết này. Không nhận
trực tiếp payload khách hàng rồi gắn `is_structured=True`.

`ReleaseAdapter` kiểm tra timestamp của snapshot trước khi dựng lịch sử: ngày
tạo/hủy, event/ingestion của scan, lần giao và báo cáo không được vượt tick và
phải có timezone. Snapshot tự cấp sai cutoff bị từ chối bằng `ValueError`;
caller cần lọc/mask qua replay trước khi gọi. Các lần giao được sắp theo thời
gian để thứ tự dòng trong projection không làm đổi kết luận lỗi khách.

`FeedHealth(feed, status, checked_at, source_timestamp, last_ingested_at=None)`
dùng status `trusted/stale/corrupt/missing` theo schema mới. Phải trusted, có
timestamp nguồn không quá 30 phút và không ở tương lai; `checked_at` và ingestion
mới không làm dữ liệu nguồn cũ thành mới. Đây không phải kiểm tra quyền liên hệ:
heartbeat A3 (ngưỡng 60 phút), control và kiểm tra lại lúc gửi thuộc platform.
A2 không tạo `ContactTask` hay `Action`.

Khóa câu hỏi quản lý bỏ qua riêng timestamp quan sát của `a2_tick_progress`;
tiến độ không đổi và không có bằng chứng mới sẽ không sinh câu hỏi lại mỗi tick.
Giá trị tiến độ và bằng chứng nguồn vẫn tham gia khóa; audit giữ đủ timestamp.
Khóa của câu hỏi có progress thay đổi so với bản cũ, nên kiểm thử/nâng cấp demo
dùng run mới; không coi đây là migration gộp các câu hỏi đã lưu bằng khóa cũ.

## Payload danh sách bàn giao Trúc

```python
from logistics_an_nguyen import (
    ReleaseReader, ReleaseAdapter, ProgressTracker,
    evaluate_tick, assessed_orders_payload,
)

with ReleaseReader("data/release_main/core_14d.sqlite") as reader:
    snapshot = reader.snapshot(current_tick)
health = tuple(health)  # Reuse the exact A3 snapshots for assessment and export.
tracker = ProgressTracker(previous_progress)
orders = tracker.apply(ReleaseAdapter(snapshot).orders(),
                       tick_at=current_tick, feed_health=health)
result = evaluate_tick(orders, tick_at=current_tick, feed_health=health)
payload = assessed_orders_payload(snapshot, result, feed_health=health)
# Persist tracker.records only after the whole tick succeeds.
```

Hàm trả envelope nội bộ `payload_version="a2_order_list_v1"`, `tick_at`,
`feed_health`, `orders`. Mỗi phần tử `orders` giữ nguyên các trường từ
`assessment_payload` và thêm:

| Trường | Ý nghĩa |
| --- | --- |
| `created_at` | Ngày đặt từ `orders.created_at`; null nếu feed orders không dùng được |
| `handed_over_at` | Event time sớm nhất của scan `handed_over` nhìn thấy; null nếu thiếu scan hoặc feed orders/scan_events không dùng được |
| `metadata_evidence` | Bằng chứng ngày đặt/bàn giao gồm bảng, record ID, ingestion và giá trị timestamp |
| `metadata_reason_codes` | `created_at_feed_unavailable`, `handed_over_scan_missing`, `handed_over_at_feed_unavailable` khi tương ứng |

Timestamp đầu ra dùng UTC ISO 8601; `guaranteed_date` vẫn là ngày Việt Nam.
Trúc hiển thị timestamp theo Asia/Ho_Chi_Minh và phân biệt ngày đặt, ngày bàn giao,
ngày cam kết, ETA mới. Không lấy ngày đặt hoặc stage station thay ngày bàn giao.
Scan bàn giao phải có cả event time và ingestion không vượt tick; scan đến muộn
chỉ xuất hiện sau khi ingest. Có nhiều lần bàn giao thì lấy lần đầu đã nhìn thấy,
tie theo ingestion rồi record ID. Retry không làm thay đổi mốc này; một scan cũ
được ingest ở tick sau có thể bổ sung/sửa mốc sớm nhất đã biết.

`feed_health` chứa status, checked_at, source_timestamp, last_ingested_at và
`usable_at_tick` cho từng feed, bao gồm missing khi chưa có A3. Status trusted
chưa đủ: UI phải đọc `usable_at_tick` để nhận biết timestamp nguồn quá hạn.
Metadata chỉ là phần bổ sung, không thay status, ETA, fault, confidence hay
reason_codes của assessment. `metadata_evidence` giữ giá trị quan sát để audit
kể cả khi feed không đáng tin; không dùng giá trị audit thay trường hiển thị null.

Đây là payload **nội bộ**, không phải response công khai hay quyền liên hệ:
Trúc phải kiểm ownership/auth, lọc bằng chứng và text nguồn trước khi trả cho
khách/shop. Không suy ra quyền liên hệ từ `usable_at_tick`: heartbeat, controls
và gate lúc gửi vẫn do platform/A3 cung cấp. Không có heartbeat giả trong payload.

Caller phải dùng cùng snapshot/tick và cùng health đã đưa vào A2. Hàm từ chối
assessment khác tick, trùng/thiếu/thừa đơn, ngày cam kết không khớp, evidence
tương lai, health trùng/tương lai hoặc bàn giao trước ngày đặt. Payload gồm đúng
tập đơn nhìn thấy chưa hủy, sắp theo order_id. Lọc theo quyền người dùng ở tầng
HTTP sau khi có payload nội bộ. `OrderAssessment` và `assessment_payload` giữ
nguyên cấu trúc; phiên bản trên chỉ thuộc adapter A2, không sửa shared contracts.

## Quy ước bằng chứng cần Huy duyệt

Mỗi fact dùng đầy đủ các trường của `contracts.types.Evidence`. Các mã dưới
đây là từ vựng adapter A2 đề xuất, **không phải schema DB release**:

| `fact_code` | Kiểu `value` | Ý nghĩa |
| --- | --- | --- |
| `logistics_stage` | status scan nguồn | Chỉ lost/damaged/return_failed tạo exception |
| `stationary_ticks` | số nguyên không âm | Số khoảng tick 30 phút liên tiếp không đổi giai đoạn/vị trí |
| `fault_party` | enum `FaultParty` | Bên chịu lỗi được bằng chứng xác nhận |
| `delivered_at` | ISO 8601 có timezone | Thời gian giao thực tế, không vượt tick |
| `revised_eta` | ISO 8601 có timezone | ETA đã được nguồn có cấu trúc xác nhận |
| `late_probability` | số hữu hạn trong [0, 1], không nhận bool | Ước lượng trễ từ nguồn/model đáng tin cậy |
| `confidence` | số hữu hạn trong [0, 1], không nhận bool | Độ tin cậy do nguồn/model cung cấp |
| `slow_safe` | bool | Chậm nhưng vẫn an toàn theo nguồn có cấu trúc |

- Chỉ `ingested_at <= tick_at` được nhìn thấy. Fact được chọn bằng ingestion
  mới nhất cho từng mã, không theo event time. Null mới nhất xóa giá trị cũ.
  Hai giá trị khác nhau cùng ingestion time gây mâu thuẫn; không chọn tùy thứ tự.
- Fact từ feed không dùng được không được dùng suy ra ETA, fault hay trạng thái
  exception. Mọi feed đóng góp bằng chứng structured đều được kiểm tra, kể cả
  adapter quên đưa vào `required_feeds`.
- Free text chỉ hạ confidence về tối đa 0,5; không quyết định status, ETA, fault,
  xác suất hoặc gọi hành động. Cả giới hạn 0,5 và semantics boolean bên trên cần
  được chốt với Huy khi có dữ liệu. Fact lạ được giữ làm provenance, không thi hành.
- ETA hết hạn bị bỏ và ghi `eta_expired`; thiếu ETA trả `None`. Không lấy ngày
  cam kết làm ETA mới. Đơn đã giao không còn ETA tương lai.
- `late_days = max(0, ngày_VN(reference) - guaranteed_date)`, với reference là
  ngày giao có bằng chứng hoặc tick. Dùng UTC+07 cho replay Việt Nam hiện đại,
  không yêu cầu gói `tzdata` trên Windows; không hỗ trợ quy tắc múi giờ lịch sử.
- Đã trễ thì xác suất sự kiện trễ là 1; đã giao đúng hẹn là 0. Đơn chưa trễ/chưa
  giao dùng xác suất từ nguồn. Chưa có forecast: confidence 0 và
  `risk_estimate_missing`; không tự coi feed là hỏng. Probability bắt buộc trong
  contract tạm là 0; **không được đọc là dự báo an toàn**. Nhãn theo D2 có thể
  là on_track khi chưa có bằng chứng thỏa nhãn khác; phải đọc cả confidence/reasons.
- Confidence thiếu là 0. Feed không dùng được, fact mâu thuẫn hoặc forecast
  thiếu cũng đặt confidence 0. Các giá trị này chưa được hiệu chỉnh thống kê.

Thứ tự predicate: stage lost/damaged/return_failed; feed không dùng được/mâu
thuẫn; fault customer; `late_days > 0`; ETA vượt ngày đảm bảo; đứng yên hai
khoảng tick liên tiếp; chậm chặng nhưng ETA vẫn trong ngày; còn lại on_track.
Ba nhãn dự báo chỉ dùng khi chưa giao. Ngưỡng p_contact/p_watch không thay các
predicate D2. Marker `exception=True` cũ không đủ để sinh nhãn exception.

Lỗi kiểu dữ liệu, timestamp không timezone, enum/số sai phạm vi bị từ chối bằng
`ValueError`; platform cần ghi incident/quarantine đầu vào đó. Hỏng một input
khiến `evaluate_tick` không trả kết quả phần nào và không ghi state.

## Supervisor và ranh giới state

Câu hỏi dùng template cho feed/mâu thuẫn, thiếu forecast, exception, trễ chưa
rõ lỗi hoặc thiếu ETA của đơn cần chú ý. ID dựa trên đơn, loại câu hỏi và bằng
chứng structured. Tick mới hoặc retry không nhân bản cùng câu hỏi. Bằng chứng
thay đổi tạo phiên review mới; các câu hỏi cũ không tự đóng. Free text không
được ghép vào lời nhắc hay ID câu hỏi.

`QuestionStore` chỉ chấp nhận SQLite in-memory hoặc file dưới `runs/` của repo,
chỉ thao tác bảng `main.supervisor_questions` đã có. Caller quản lý transaction.
Trả lời cùng nội dung và người trả lời là idempotent; đổi một câu trả lời đã lưu
bị từ chối. Nội dung trả lời không tự trở thành fact. Để thay đổi assessment,
platform phải cung cấp bằng chứng structured mới đã được kiểm chứng.

Không ghi source DB, ledger, outbox, heartbeat, controls hay dữ liệu world.
Không tính/chọn tiền, không cấp xu, không tự mở liên hệ. Đầu ra evidence có thể
chứa text gốc: A1 phải tiếp tục coi đó là dữ liệu không đáng tin; HTTP route phải
lọc trường nội bộ/quyền truy cập trước khi trả cho khách hoặc shop.

## Bàn giao cần Huy/Truc xử lý

1. Đã có DB release và adapter A2. Huy nối `ReleaseReader`/`ReleaseAdapter` sau
   A3 và trước A1, thống nhất tên feed theo các bảng nguồn bên dưới.
2. D2/freshness đã cập nhật theo Huy; còn cần review confidence cap, cách biểu
   diễn thiếu forecast và mapping fault. Huy ghi quyết định chung trong docs.
3. Huy và An Nguyen kiểm định baseline survival mới theo nhiều tick, thống nhất
   nhóm tuyến và tiêu chí chất lượng trước khi dùng tự động cho khách hàng.
4. Trúc gắn `assessed_orders_payload` vào API orders/shop và QuestionStore vào API supervisor,
   thêm UI, auth, phân quyền và xử lý lỗi; Huy giữ transaction/checkpoint của tick.
5. Truc đọc `OrderAssessment`, reason/evidence và kiểm tra guard qua platform;
   không suy diễn eligibility xu từ riêng status hoặc probability.

Không có HTTP server hay vòng replay A3 → A2 → A1 hoàn chỉnh trong phần A2 này. Các mục
trên là yêu cầu bàn giao trong repository, chưa được gửi cho thành viên khác.

## Kiểm thử

```powershell
.venv/Scripts/python.exe -m pytest -q acceptance_an_nguyen
.venv/Scripts/python.exe -m pytest -q acceptance_huy/test_assessed_order_handoff.py
.venv/Scripts/python.exe -m pytest -q
```

Cài môi trường theo `requirements/dev.txt` do Huy sở hữu. Test dùng fixture
trong test và SQLite in-memory/temporary; không cần DB release, không tạo world data.

## Adapter dữ liệu release và chạy local

```powershell
.venv/Scripts/python.exe -m logistics_an_nguyen --tick 2026-10-28T12:00:00+07:00
```

Lệnh mặc định đọc `data/release_main/core_14d.sqlite`, đọc health từ
`runs/state.sqlite` nếu đã có, ghi JSONL assessment, payload danh sách
`<tick>.orders.json` và summary vào `runs/a2/`. Summary có `order_list_file`
để Trúc tìm file bàn giao; JSONL assessment cũ giữ nguyên cấu trúc. File danh sách
được ghi qua file tạm rồi replace để reader không đọc phải JSON đang ghi dở.
Không tạo state A3 giả, không thay đổi DB nguồn, không ghi ledger/outbox/câu hỏi.
`--core`, `--state`, `--output` cho phép đổi nguồn/state/đích; output phải nằm
trong `runs/`. Tick bắt buộc có timezone, không dùng giờ máy làm thời gian nghiệp vụ.

```python
from logistics_an_nguyen import ReleaseReader, ReleaseAdapter, ProgressTracker, evaluate_tick

# Execute after A3; health contains the real snapshots from this replay tick.
with ReleaseReader("data/release_main/core_14d.sqlite") as reader:
    snapshot = reader.snapshot(current_tick)
orders = ReleaseAdapter(snapshot).orders()
tracker = ProgressTracker(previous_progress)
orders = tracker.apply(orders, tick_at=current_tick, feed_health=health)
result = evaluate_tick(orders, tick_at=current_tick, feed_health=health)
# Persist tracker.records in runtime state only after the tick succeeds.
```

`ReleaseReader` là lớp harness đọc allowlist cột, bằng SQL có tham số cutoff,
qua SQLite URI `mode=ro` và `query_only`. Chỉ lớp này giữ kết nối source;
estimator chỉ nhận projection as-of. Đây là projection trong bộ nhớ, không
phải công cụ cắt toàn bộ DB vật lý `cut_at.py` được nhắc trong QUICKSTART
(công cụ đó chưa có trong repo). Harness kiểm thử chính thức vẫn cần Huy cung
cấp bản cắt vật lý nếu quy trình đánh giá yêu cầu. Adapter cũng đọc được
`core_asof.sqlite` có cùng schema qua `--core`.

Các cột thời gian nguồn dùng ISO giây với offset `+07:00` theo schema đã kiểm
tra; cutoff được đổi về cùng định dạng. Không dùng SQLite `datetime()` để so sánh.

| Bảng | Cột thời gian quyết định khả năng nhìn thấy | Cách dùng |
| --- | --- | --- |
| `orders` | `created_at` | Ngày đảm bảo, hãng, service; che `cancelled_at` tương lai |
| `scan_events` | `ingested_at`, đồng thời không nhận event tương lai | Giai đoạn, giao xong, ngoại lệ, thời gian ở giai đoạn |
| `delivery_attempts` | `attempt_at` (schema không có ingestion riêng) | Giao thành công, mã lý do và số cuộc gọi |
| `linehaul_reports` | `reported_at` (schema không có ingestion riêng) | Chỉ thêm báo cáo chưa xác minh của chuyến đang đi |

Đọc bảng không có `ingested_at` dùng thời điểm availability theo D5 của Huy.
Không đọc `truth_main.sqlite`,
`main/`, `heldout/`, ledger, ticket, số tiền hay thông tin định danh khách.
`ops_14d.sqlite` dành cho A3; adapter A2 chưa tự kết luận feed khỏe từ telemetry.

- Lọc ingestion trước; chọn scan cuối theo **event time**, tie theo thứ tự vòng
  đời. Vì scan hãng có thể tới muộn, scan cũ ingest mới không được kéo lùi giai đoạn.
- Retry có `carrier_event_id` được gộp theo đơn/ID; scan nội bộ không có ID được
  gộp khi cùng trạng thái/vị trí và cách bản giữ lại dưới 120 giây.
- Đơn đã hủy ở tick bị loại khỏi tập đánh giá. Chỉ `lost`, `damaged`,
  `return_failed` tạo exception. Returning/returned/waiting_to_return ngừng dự
  báo giao hàng nhưng không tự thành exception; vẫn theo thứ tự D2.
- Fault customer cần mã/outcome khớp: không liên lạc được có ít nhất 3 cuộc gọi;
  từ chối hoặc xin hẹn lại có ít nhất 1 cuộc gọi. `wrong_address` chưa đủ để
  phân biệt lỗi khách và lỗi phân giải địa chỉ nên giữ unknown.
- Scan mất/hỏng tại kho quy về platform; tại station/trip/sorting_center quy
  về carrier. Đây là mapping đề xuất cần chủ contract duyệt, không phải nhãn đáp án.
- `linehaul_reports.reason_code` cũng là lời người nhập có thể sai: cả mã và
  ghi chú đều unstructured. Không suy ra force majeure từ riêng báo cáo thời tiết.

## Baseline ETA/xác suất từ lịch sử đã nhìn thấy

`forecast.py` dùng Kaplan–Meier theo `(carrier_id, service_level, stage)`:

1. Lấy thời gian từ lần gần nhất vào giai đoạn đến giao thành công đã nhìn thấy.
2. Đơn chưa giao vẫn tham gia dưới dạng right-censored tại tick; đơn kết thúc
   không giao bị censor tại thời điểm kết thúc. Không loại sạch đơn chậm đang chờ.
   Nếu hoàn/hủy hoặc terminal không giao xảy ra trước hay cùng lúc một bản ghi
   giao thành công, lịch sử huấn luyện dừng tại terminal và không tính là mẫu
   giao thành công. Các chặng sau mốc kết thúc không được đưa lại vào cohort.
3. Điều kiện hóa theo số giờ đơn hiện tại đã ở giai đoạn; tính xác suất vẫn
   chưa giao sau cuối ngày đảm bảo và ETA trung vị của thời gian còn lại.
4. Chỉ trả forecast khi còn ít nhất 20 mẫu phù hợp tuổi giai đoạn và ít nhất
   5 mẫu đã giao. Không ngoại suy vượt phần đuôi chưa quan sát; ETA có thể None
   nếu chưa xác định được trung vị. Giao đúng nửa đêm ngày kế tiếp được tính trễ.

Độ chậm chặng so với trung vị thời gian chuyển giai đoạn của ít nhất 20 lượt
đã nhìn thấy. Chỉ tạo slow_safe khi chậm chặng **và** ETA vẫn kịp ngày đảm bảo.

`ProgressTracker` theo dõi giai đoạn/vị trí qua các tick: quan sát đầu là 0,
sau hai khoảng 30 phút không đổi là 2 (watch). Retry cùng tick không tăng;
đổi giai đoạn/vị trí, mất trust hoặc bỏ tick thì reset. CLI lưu `progress.json`
dưới output runtime. Replay lùi cần thư mục `--output` riêng, không dùng state
của tương lai. Với Python API, caller lưu `tracker.records` sau tick thành công.

Đây là baseline **chưa hiệu chỉnh thống kê**, không phải cam kết giao hàng.
Confidence chỉ là điểm hỗ trợ dựa trên số mẫu/tỷ lệ đã giao, tối đa 0,8. Nhóm
carrier/service/stage chưa tách theo tuyến, giờ/ngày hay sự cố; các ca hoàn/hủy
có thể vi phạm giả định censor độc lập. Cần kiểm định trước khi dùng tự động.

Evidence dẫn xuất ghi `a2_survival_v1`, mã cohort hash theo các mẫu, số mẫu,
số mẫu đã giao, phiên bản phương pháp và tick. Không tạo record nguồn giả.
Forecast được gắn phụ thuộc cả ba feed `orders`, `scan_events`,
`delivery_attempts`: thiếu/bad một feed sẽ chặn sử dụng ETA/xác suất dẫn xuất,
không chỉ giảm confidence rồi vẫn đưa ETA cho khách.

Chạy thực tế tại `2026-10-28T12:00:00+07:00`: 11.008 đơn nhìn thấy,
815 đơn đã hủy, 10.193 đơn được xử lý, 74.028 scan và 7.230 lần giao;
3.230 đơn có baseline forecast. Khi chưa có health từ A3, toàn bộ assessment
là `unknown_feed`, đúng cơ chế chặn; các số trên không phải điểm chất lượng
dự báo và không chứng minh forecast chính xác.

## Công cụ kiểm định ETA với cửa sổ theo dõi cố định

```powershell
.venv/Scripts/python.exe -m logistics_an_nguyen.validation --tick 2026-10-25T12:00:00+07:00 --tick 2026-10-26T12:00:00+07:00 --tick 2026-10-27T12:00:00+07:00 --followup-hours 72 --observed-through 2026-10-30T12:00:00+07:00 --output runs/a2-validation/20261031-72h
```

`--tick` lặp được, bắt buộc có timezone và không trùng instant. Mỗi tick dùng
outcome cutoff đúng `tick + followup_hours`; cửa sổ mặc định là 72 giờ, phải là
số nguyên dương. `--observed-through` là mốc quan sát do người chạy khai báo,
không phải giờ máy hoặc bằng chứng feed đầy đủ. Lệnh từ chối tick có cửa sổ
vượt mốc này; không âm thầm rút ngắn thời gian theo dõi. Người chạy cần chọn mốc
nằm trong phạm vi dữ liệu có sẵn. Dù được khai báo, thiếu outcome vẫn là unknown.

`--core` cho phép dùng bản core as-of có cùng schema. Công cụ từ chối đường dẫn
truth/heldout, mở SQLite read-only và so SHA-256 trước/sau. Mọi forecast được
đóng băng trước khi đọc bất kỳ snapshot outcome nào; outcome không đi ngược
vào model. Tất cả snapshot vẫn theo availability/ingestion của `ReleaseReader`.
Chưa có A3 cũng chạy được kiểm định candidate forecast offline: không tạo health,
không cho quyền liên hệ, không đổi thuật toán hoặc xuất production assessment.

Kết quả là `<output>/report.json`, ghi qua file tạm rồi replace; output phải
nằm trong `runs/`. Chạy lại cùng đầu vào tạo cùng báo cáo. Report giữ SHA-256
nguồn và SHA-256 các prediction scalar đã đóng băng để đối chiếu replay.
Python API `logistics_an_nguyen.validation.validate_release(core_path, ticks=...,
followup_hours=..., observed_through=...)` trả dict và không ghi output.

| Phần báo cáo | Cách đọc |
| --- | --- |
| `summary`, `ticks`, `groups` | Toàn bộ lượt quan sát, từng tick và từng nhóm `(carrier_id, service_level, stage)` tại thời điểm dự báo |
| `active_observations`, `forecast_count`, `forecast_coverage` | Đơn active gồm cả trường hợp không đủ lịch sử để có forecast; mẫu số không chỉ là đơn có dự báo |
| `distinct_orders`, `distinct_forecast_orders` | Số đơn duy nhất; một đơn xuất hiện qua nhiều tick tạo nhiều lượt quan sát có tương quan |
| `outcome_counts` | Giao được quan sát, chưa có outcome, terminal trước delivery, hoặc delivery thực tế đã xảy ra trước tick nhưng chưa thấy lúc dự báo |
| `eta_scored`, `eta_mae_hours`, `eta_bias_hours` | Chỉ chấm forecast có ETA và delivery sau tick trong cửa sổ; bias = ETA trừ thực tế, âm nghĩa dự báo quá sớm |
| `risk_exclusion_counts` | Đã trễ tại tick, deadline ngoài cửa sổ, terminal trước delivery hoặc delivery đã xảy ra trước tick |
| `risk_known_labels`, `risk_unknown_labels` | Nhãn đủ điều kiện đã biết và chưa biết; không gán thiếu delivery thành đúng hạn/trễ |
| `lateness_brier_complete_case`, `always_on_time_brier_complete_case` | Bình phương sai số xác suất và baseline luôn dự báo không trễ, cùng tập nhãn được chấm; thấp hơn tốt hơn |
| `*_brier_lower_bound`, `*_brier_upper_bound` | Cận tốt/xấu nhất trên tập risk không terminal khi nhãn chưa biết có thể là 0 hoặc 1; không phải khoảng tin cậy hoặc ước lượng đã hiệu chỉnh censoring |
| `calibration_bins` | Năm khoảng xác suất rộng 0,2; cận dưới đóng, cận trên mở, khoảng cuối gồm 1. Báo số nhãn biết/chưa biết, xác suất trung bình và tỷ lệ trễ chỉ trên nhãn biết |

Để tránh chọn riêng những ca giao sớm dễ chấm, risk chỉ được chấm nếu deadline
đã kết thúc trong cửa sổ theo dõi, kể cả ca đã giao đúng hạn nhưng deadline còn
ở tương lai. Giao đúng 00:00 ngày sau ngày cam kết được tính trễ. Đơn chưa giao
vẫn được tính vào độ phủ và nhóm outcome chưa biết. Đơn có terminal trước
delivery được loại riêng khỏi risk, không biến thành nhãn “không trễ”.

Đánh giá đồng cửa sổ giúp giảm khác biệt thời gian theo dõi, **không loại bỏ
selection bias/censoring**. MAE và calibration vẫn chỉ phản ánh các delivery
đã quan sát; nhóm nhỏ có thể rất nhiễu. Không chọn model/tham số hoặc quyết định
tự động liên hệ chỉ từ báo cáo này. Các cận của model và baseline không được
so chéo như thể cùng một cách gán nhãn chưa biết.

Lần chạy 31/10/2026 với lệnh trên: 10.604 lượt active, 8.497 lượt có forecast
(80,13%); 4.987 ETA được chấm, MAE gộp 16,55 giờ. Có 3.015 forecast chưa thấy
delivery và 493 terminal trước delivery. Report có 44 nhóm. SHA-256 nguồn không đổi.

| Tick 12:00 giờ VN | Cutoff sau 72 giờ | ETA được chấm | MAE ETA (giờ) | Risk biết/chưa biết nhãn | Brier model / luôn không trễ |
| --- | --- | --- | --- | --- | --- |
| 25/10 | 28/10 12:00 | 1.334 | 11,70 | 705 / 43 | 0,0600 / 0,0170 |
| 26/10 | 29/10 12:00 | 1.842 | 15,53 | 864 / 55 | 0,1113 / 0,0602 |
| 27/10 | 30/10 12:00 | 1.811 | 21,16 | 950 / 81 | 0,1571 / 0,1421 |

Brier gộp trên 2.519 nhãn biết là 0,1142, baseline là 0,0790; còn 179 nhãn
chưa biết trong tập risk không terminal đủ thời hạn. Cận model 0,1111–0,1497
và baseline 0,0738–0,1401 còn chồng nhau, nên không suy kết luận toàn tập chỉ từ
complete-case score. Chưa xác nhận mô hình đủ chất lượng để dùng tự động.

Test: `.venv/Scripts/python.exe -m pytest -q acceptance_huy/test_forecast_validation.py`.
Ma trận case platform chờ interface thật nằm trong
`../.scratch/specs/a2-platform-acceptance.md`; không phải các test tích hợp đã chạy.

Đợt kiểm tra sâu A2 ngày 31/10/2026 gồm kiểm thử pipeline nhiều tick, retry,
khôi phục progress, cutoff, training terminal và ghép với transaction/state nền
của Huy. Xem [báo cáo và giới hạn](../.scratch/research/a2-verification.md).

## Kiểm tra offline ban đầu ngày 31/10/2026 (cách cũ)

Lần thử dưới đây dùng một cutoff chung nên thời gian theo dõi giữa các tick khác
nhau; giữ để đối chiếu lịch sử. Dùng CLI cửa sổ cố định bên trên cho các lần chạy
mới. Tập risk ở cách mới còn yêu cầu deadline đã kết thúc trong cửa sổ, nên không
so trực tiếp Brier của hai cách như cùng một tập nhãn.

Đóng băng forecast ở 12:00 giờ Việt Nam ngày 25, 26, 27/10 trước khi đọc
outcome as-of 28/10/2026 12:00. Chỉ dùng `release_main/core_14d.sqlite`; không
dùng truth/heldout, không tạo health A3. Hash cả core/ops không đổi sau khi chạy.

| Tick (giờ VN) | Đơn đang vận chuyển có forecast | Số ETA có outcome để chấm | MAE ETA (giờ) | Brier xác suất trễ |
| --- | --- | --- | --- | --- |
| 25/10 12:00 | 2.346 / 3.436 (68,3%) | 1.334 | 11,70 | 0,0486 |
| 26/10 12:00 | 3.149 / 3.558 (88,5%) | 1.316 | 15,49 | 0,0655 |
| 27/10 12:00 | 3.002 / 3.610 (83,2%) | 547 | 10,80 | 0,0620 |

MAE tính trên forecast có ETA và đã nhìn thấy giao thành công sau tick; Brier
tính trên các đơn trong tập này chưa trễ tại tick và có dự báo xác suất, gồm
1.248, 1.309, 545 đơn. Brier càng thấp càng tốt. Trên các mẫu được chấm này,
dự báo hằng số không trễ có Brier tương ứng 0,0096 / 0,0099 / 0,0147, thấp hơn
baseline hiện tại. Do đó chưa có cơ sở dùng xác suất hiện tại để tự động chọn
khách cần liên hệ.

Đây là kiểm tra thăm dò có **selection bias**: 1.012 / 1.832 / 2.455 forecast
chưa có outcome giao hàng tại cutoff và bị bỏ khỏi phép chấm, không bị gán là
đúng hạn hay trễ. Tập đơn lặp qua các tick; thời gian theo dõi khác nhau và chưa
đánh giá đầy đủ đơn bị censor/hủy. Các số trên không phải chất lượng toàn tập
hay cam kết giao hàng. Cần đánh giá với thời gian theo dõi đủ, xử lý censoring
và chốt tiêu chí với Huy trước khi hiệu chỉnh hoặc dùng tự động.

Artifact local được gitignore: `runs/handoff-review-20261031/baseline-validation.json`
và script tái lập `runs/handoff-review-20261031/validate_baseline.py`.
