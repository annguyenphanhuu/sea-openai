# A2 — phần việc của An Nguyen

A2 nhận snapshot đơn hàng, bằng chứng logistics, trạng thái feed từ A3 và thời
gian tick; trả về đúng một `contracts.types.OrderAssessment` cho mỗi đơn cùng
các câu hỏi cần quản lý xác minh. Mã chạy bằng Python 3.11+, chỉ dùng thư viện
chuẩn. Các quy ước bên dưới là **quy ước nội bộ A2 để tích hợp thử**, không sửa
hay thay thế quyết định chung trong `docs/decisions.md`.

## Phân tích và tình trạng công việc

| Việc An Nguyen phụ trách | Tình trạng |
| --- | --- |
| Phân loại theo thứ tự `STATUSES` | Đã triển khai trong `assessment.py` |
| Tính ngày trễ theo ngày Việt Nam, dừng khi đã giao | Đã triển khai |
| Chọn ETA, fault và risk từ bằng chứng có cấu trúc | Đã triển khai; không tự dựng mô hình dự báo |
| Lọc dữ liệu theo `ingested_at`, kiểm tra dữ liệu đầu vào | Đã triển khai trên snapshot do platform cung cấp |
| Câu hỏi quản lý, lưu/đọc/trả lời và chống trùng khi retry | Đã triển khai trong `service.py` và `questions.py` |
| Đầu ra JSON cho API orders/shop và review | Đã có Python API và serializer để Huy gắn HTTP route |
| Kiểm thử biên và lỗi A2 | Đã có trong `acceptance_an_nguyen/` |
| Adapter đọc DB release, xác suất/ETA dự báo thực tế | Chờ DB nguồn và schema; không đoán tên bảng hay tạo world data |
| Chạy chuỗi A3 → A2 → A1, HTTP/auth và checkpoint | Huy tích hợp; A1 do Truc phụ trách |

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

`FeedHealth(feed, status, checked_at)` là snapshot nội bộ với status theo schema
chung. Snapshot thiếu, không healthy, ở tương lai hoặc quá 60 phút được xem là
không dùng được. Quy tắc freshness này là mặc định A2 cần Huy chốt. Đây không
phải kiểm tra quyền liên hệ: heartbeat/control và kiểm tra lại tại lúc gửi vẫn
thuộc A3/platform. A2 không tạo `ContactTask` hay `Action`.

## Quy ước bằng chứng cần Huy duyệt

Mỗi fact dùng đầy đủ các trường của `contracts.types.Evidence`. Các mã dưới
đây là từ vựng adapter A2 đề xuất, **không phải schema DB release**:

| `fact_code` | Kiểu `value` | Ý nghĩa |
| --- | --- | --- |
| `exception` | bool | Có ngoại lệ logistics đang hiệu lực |
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
  giao dùng xác suất từ nguồn. Chưa có forecast: trả `unknown_feed`, confidence
  0 và `risk_estimate_missing`. Trường probability bắt buộc trong contract v0
  tạm là 0 trong trường hợp này; **không được đọc là dự báo an toàn**.
- Confidence thiếu là 0. Feed không dùng được, fact mâu thuẫn hoặc forecast
  thiếu cũng đặt confidence 0. Các giá trị này chưa được hiệu chỉnh thống kê.

Thứ tự predicate: `exception=True`; feed không dùng được/mâu thuẫn/thiếu
forecast; fault customer; `late_days > 0`; xác suất >= 0,7; xác suất >= 0,2;
`slow_safe=True`; còn lại `on_track`. Ba nhãn dự báo chỉ dùng khi chưa giao.
Các trạng thái exception/customer_fault chỉ hết hiệu lực khi nguồn ingest bản
cập nhật rõ ràng; A2 không tự đoán rằng giao xong đã giải quyết mọi ngoại lệ.

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

1. Huy cung cấp DB release, schema và mapping các fact; sau đó An Nguyen viết
   adapter thật và kiểm thử replay với dữ liệu nguồn chỉ đọc.
2. Huy duyệt predicates, freshness, confidence cap, missing-forecast sentinel
   và từ vựng fact; ghi quyết định đã duyệt vào `docs/decisions.md` (Huy sở hữu).
3. Huy chọn nguồn/mô hình dự báo cùng An Nguyen, cung cấp provenance và kiểm
   định xác suất/ETA. Hiện chưa có thuật toán học hay dự báo thời gian giao mới.
4. Huy gắn serializer vào API orders/shop và QuestionStore vào API supervisor,
   thêm auth, phân quyền, xử lý lỗi và transaction/checkpoint của tick.
5. Truc đọc `OrderAssessment`, reason/evidence và kiểm tra guard qua platform;
   không suy diễn eligibility xu từ riêng status hoặc probability.

Không có HTTP server hay vòng replay hoàn chỉnh trong phần A2 này. Các mục
trên là yêu cầu bàn giao trong repository, chưa được gửi cho thành viên khác.

## Kiểm thử

```powershell
.venv/Scripts/python.exe -m pytest -q acceptance_an_nguyen
.venv/Scripts/python.exe -m pytest -q
```

Cài môi trường theo `requirements/dev.txt` do Huy sở hữu. Test dùng fixture
trong test và SQLite in-memory; không cần DB release, không tạo dữ liệu world.
