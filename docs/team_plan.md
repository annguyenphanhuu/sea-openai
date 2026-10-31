# Team plan — hackathon đơn trễ, 7 giờ

Team: **Huy, An Nguyen, Trúc**. Viết mới theo yêu cầu Huy ngày 31/10/2026. D1–D5 là quyết định đã chốt; lịch giờ và route dưới đây là kế hoạch triển khai. Repo hiện có scaffold/contracts/tests, chưa có agent, API server, UI hoặc executor chạy thật.

## 1. Cấu trúc folder và quyền sở hữu

### 1.1. Folder

| Folder | Nội dung | Người sửa |
| --- | --- | --- |
| `contracts/` | Types, permission matrix, params, schema | Chỉ Huy |
| `requirements/` | Dependencies runtime/dev | Chỉ Huy |
| `platform_huy/` | Replay, state, A3, execute_action, API tích hợp, UI quản lý | Huy |
| `logistics_an_nguyen/` | A2: trạng thái, ETA, bằng chứng, câu hỏi supervisor | An Nguyen |
| `care_truc/` | A1: chat/web voice, rules, template/validator, handoff | Trúc |
| `acceptance_huy/` | Test chéo cho platform/A3 của Huy | An Nguyen |
| `acceptance_an_nguyen/` | Test chéo cho A2 của An Nguyen | Trúc |
| `acceptance_truc/` | Test chéo cho A1 của Trúc | Huy |
| `docs/` | Plan, decisions, data audit, hướng dẫn | Huy tổng hợp ý kiến team |
| `data/release_main/`, `data/tiny/` | DB và tài liệu nguồn, gitignore | Chỉ đọc |
| `runs/` | State/checkpoint/output của mỗi lần chạy, gitignore | Runtime tạo |

Tên `acceptance_<người>` chỉ người được kiểm thử. Không sửa code/test của người khác để làm test xanh. Đợt sửa scaffold hiện tại được Huy yêu cầu cập nhật test contract có sẵn trong `acceptance_huy/`; sau bàn giao An Nguyen quản lý folder này. Huy sở hữu cấu hình root và `AGENTS.md`.

### 1.2. Luồng tổng thể

Mỗi tick 30 phút: dữ liệu được phép thấy → **A3 → A2 → A1** → outbox/platform. A3 kiểm độ tin feed; A2 đánh giá logistics; A1 tương tác khách. Output vào state riêng, không ghi DB nguồn. Chỉ platform thực hiện tiền qua một cổng có kiểm quyền. Mọi chức năng UI phải có API.

## 2. Hợp đồng chung: types, schema, params, API

### 2.1. Types

Nguồn dùng chung là `contracts/types.py`; không copy enum sang module riêng.

- `STATUSES`: `exception`, `unknown_feed`, `customer_fault`, `late`, `at_risk`, `watch`, `slow_safe`, `on_track` theo thứ tự ưu tiên.
- `INTENTS`: `unreasonable_abusive`, `ask_human`, `want_cancel`, `want_more`, `ask_why`, `accept`, `off_topic` theo thứ tự khai báo.
- `OrderAssessment`: `order_id`, `assessed_at`, `status`, `guaranteed_date`, `revised_eta`, `late_days`, `late_probability`, `confidence`, `fault_party`, `reason_codes`, `evidence`. ETA có thể None; không bịa ngày.
- `ContactTask`: `contact_id`, `order_id`, `assessment_at`, `created_at`, `channel`, `proactive`, `reason_code`, `idempotency_key`. Channel là `chat` hoặc `web_voice`.
- `Action`: `action_id`, `order_id`, `kind`, `amount_vnd: int`, `source`, `requested_at`, `idempotency_key`, `evidence_ref: str`, `needs_approval: bool`, `queue: str`, `confirmation_id: str | None`. Không có `actor`, `contact_id`, `evidence_refs`. Queue là tên hàng đợi platform định tuyến; evidence_ref trỏ tới bằng chứng đã lưu.

| ActionKind | ALLOWED_SOURCES |
| --- | --- |
| `coins` | `a1` |
| `cancel_request` | `a1`, `app` |
| `eta_notice` | `a1` |
| `voucher` | `rule` |
| `refund` | `cancel_reviewer` |
| `shipping_fee_refund` | `cancel_reviewer` |

Action là yêu cầu, không phải giấy phép thực thi. Executor xác thực source từ ngữ cảnh server, số tiền theo luật, confirmation/review và điều kiện nghiệp vụ. Type hints chưa thay runtime validator. Datetime Python có timezone; wire/state dùng UTC ISO 8601; adapter chuyển timestamp nguồn +07:00 và giữ guaranteed_date là ngày VN.

### 2.2. State và params

`schema_state.sql` tạo 8 bảng: `outbox`, `ledger_new`, `contact_log`, `guard_heartbeat`, `feed_health`, `incidents`, `supervisor_questions`, `controls`.

- Outbox lưu Action, lịch xử lý, status; CHECK kind/source và UNIQUE idempotency key.
- Ledger hiện dành cho xu bù: UNIQUE idempotency key/order_id. Trước khi thực thi voucher/refund/hoàn phí ship, Huy phải bổ sung lưu vết riêng hoặc migration phù hợp; không nhét các khoản này vào `amount_xu` hiện tại.
- Contact log lưu phiên chat/web voice, lượt nói/chửi, kết quả cuộc gọi/handoff.
- Guard heartbeat lưu A3 mỗi tick và agent_id; feed health lưu `trusted/stale/corrupt/missing`, timestamp nguồn tách riêng ingestion/check time.
- Incidents, supervisor questions, controls phục vụ quản lý, câu hỏi A2 và giới hạn đang áp dụng. State khởi tạo rỗng, không phải dữ liệu thế giới cần sinh sẵn.

Params: `tick_min=30`, `p_contact=0.7`, `p_watch=0.2`, `feed_stale_max_min=30`, `guard_heartbeat_max_min=60`, `max_turns=8`. Ngưỡng xác suất không lấn át thứ tự D2 hoặc gate A3.

`late_xu_for(items_value_vnd)`: 5%, làm tròn xuống nghìn, min 10.000/max 1.000.000; None/0 → 10.000. Không dùng LLM hoặc float để tính tiền; hàm không xét eligibility.

### 2.3. Danh sách API phải triển khai

Huy sở hữu route/auth/state, An Nguyen cung cấp logic A2, Trúc cung cấp logic A1. Các route dưới đây chưa hoạt động trong scaffold.

| Chức năng | Route dự kiến | Logic |
| --- | --- | --- |
| Đơn/assessment | `GET /api/orders`, `GET /api/orders/{id}`, `GET /api/orders/{id}/assessment` | Huy + An Nguyen |
| App khách/trang shop | `GET /api/customer/orders`, `GET /api/shop/orders` | Huy, lọc chủ đơn |
| Chat | `POST /api/chats`, `GET/POST /api/chats/{id}/messages` | Trúc |
| Web voice | `POST /api/voice/sessions`, `POST /api/voice/sessions/{id}/end` | Trúc; API trả session negotiation |
| Giám sát cuộc gọi | `GET /api/calls`, `GET /api/calls/{id}` | Huy + Trúc |
| Hủy/xác nhận lần hai | `POST /api/orders/{id}/cancel-requests`, `POST /api/cancel-requests/{id}/confirm` | A1/app → Huy |
| Hàng chờ/phê duyệt | `GET /api/review-queue`, `POST /api/actions/{id}/review` | Huy, cancel_reviewer |
| Chuyển người | `POST /api/chats/{id}/handoff`, `GET /api/handoffs` | Trúc + Huy |
| Câu hỏi A2 | `GET/POST /api/supervisor-questions`, `POST /api/supervisor-questions/{id}/answer` | An Nguyen + Huy |
| Trạng thái A3 | `GET /api/guard`, `GET /api/feed-health`, `GET /api/incidents` | Huy |
| Controls | `GET /api/controls`, `PATCH /api/controls/{key}` | Huy, kiểm quyền A3 chỉ siết |
| Lịch sử action | `GET /api/orders/{id}/actions` | Huy |

Mutation phải chống retry bằng idempotency, kiểm ownership/quyền server-side. Không có endpoint cho LLM/client tự cấp tiền; xu đi qua text chat theo D4. Team chọn framework và provider/transport voice trong giờ đầu; chỉ Huy thêm requirements. Scaffold này chưa tự chọn dependency.

## 3. Chia việc theo 7 giờ, 3 nhánh

Giờ tính từ lúc team bắt đầu thực thi plan. Nhánh tích hợp cá nhân: Huy `huy`, An Nguyen `an-nguyen`, Trúc `truc`. Guardrail mới trên main yêu cầu checkout nhánh tác vụ `<type>/<lowercase-kebab-description>` để commit/push, ví dụ `feat/huy-replay`; nhánh cá nhân vẫn là đích tích hợp khi được yêu cầu. Giữ các kiểm tra tên nhánh, không sửa test để bỏ qua chúng. Lấy nền từ main đã thống nhất; giữ branch đang làm, không xóa/recreate để cập nhật.

| Giờ | Huy — platform/A3 | An Nguyen — A2 | Trúc — A1 |
| --- | --- | --- | --- |
| 0–1 | Chốt contracts/API; schema/hash nguồn; state; chọn stack cùng team | Mapping evidence, 8 nhãn, ngày cam kết | 7 intent, template, adapter chat/voice |
| 1–2 | Replay read-only/cursor/che tương lai; A3 heartbeat/feed | D1/D2, exception, customer fault, trạng thái | Rules, session text, max_turns, đếm chửi, handoff |
| 2–3 | Gate A3; execute_action/permission/idempotency; thiết kế ledger cho các loại tiền | ETA/risk, watch 2 tick, slow_safe, câu hỏi supervisor | Validator, xác nhận hủy, điều kiện D4 |
| 3–4 | API quản lý/khách/shop, queue/review; test chéo A1 | Adapter assessment; test chéo platform/A3 | Adapter chat/web voice; test chéo A2 |
| 4–5 | Ghép A3→A2→A1; guard trước gửi; UI danh sách/hàng chờ | Ghép replay; sửa lỗi test Trúc báo | Ghép platform, log voice/handoff; sửa lỗi test Huy báo |
| 5–6 | Tích hợp API/auth, retry/double-grant; sửa lỗi An Nguyen báo | Kiểm nhãn/ETA trên release, chống future leakage/free-text fault | Kiểm injection, hủy, text/voice và từ chối xu đúng |
| 6–7 | Khóa contracts, regression, merge được duyệt, chạy demo/reset state | Chọn case có bằng chứng, ghi giới hạn | Hoàn thiện flow demo và fallback voice/LLM |

Ưu tiên một tick thật qua ba agent trước khi mở rộng UI. Voice chưa sẵn thì báo chưa hoàn thành, không gọi hotline hay giả kết quả. Không dùng LLM bịa dữ liệu thiếu. Ai sở hữu implementation người đó sửa lỗi do test chéo phát hiện.

## 4. Thứ tự merge

1. Huy: contracts/schema/params/docs làm nền; import và pytest xanh.
2. Huy: replay/state/A3 và interface executor/API để A2/A1 ghép.
3. An Nguyen: A2 và test platform do An viết; chạy test A2 do Trúc cung cấp.
4. Trúc: A1 và test A2 do Trúc viết; chạy test A1 do Huy cung cấp.
5. Huy: test A1, tích hợp API/UI/voice và regression toàn luồng; giải quyết conflict cùng chủ folder.

Đưa test chéo cho chủ implementation chạy sớm trước merge. Không đổi contract âm thầm; mọi đổi contract qua Huy và thông báo hai bên dùng. Theo yêu cầu mới của Huy, **mỗi phần hoàn thành và kiểm tra đạt phải commit rồi push lên nhánh huy của repo team** (`upstream` trong checkout hiện tại). Merge vào main khi Huy yêu cầu. Các thành viên tiếp tục dùng nhánh cá nhân của mình.

## 5. Test chéo ai viết cho ai

| Tác giả | Kiểm thử | Folder | Ca bắt buộc |
| --- | --- | --- | --- |
| An Nguyen | Huy | `acceptance_huy/` | Hash DB bất biến, cursor không mất dòng cùng timestamp, che tương lai, stale nguồn >30 phút, heartbeat thiếu/quá hạn chặn, A3 chỉ siết, permission, retry không cấp trùng |
| Trúc | An Nguyen | `acceptance_an_nguyen/` | Thứ tự 8 nhãn, exception đúng 3 mã, same-day không late, ETA qua ngày mới at_risk, watch 2 tick, slow_safe, chữ tài xế không đổi fault |
| Huy | Trúc | `acceptance_truc/` | 7 intent, rules trước LLM, chặn tiền/ngày/lời hứa lạ, hủy xác nhận lại, xin người/chửi 3 lần, text chat A1 mới xét xu, voice không cấp xu |

Fixture nhỏ chỉ kiểm thuật toán/lỗi, không đưa vào replay như world data mới. Test release mở DB read-only và dùng state riêng. Tiny không đủ kiểm D1/A3 vì thiếu ngày cam kết và telemetry. Phân biệt DB constraint với business rule; pytest xanh trên scaffold chưa chứng minh end-to-end.

Từ root chạy `python -c "import contracts"`, rồi `pytest -q`. Có thể chạy riêng từng acceptance folder; trước merge chạy cả ba.

## 6. Quyết định D1–D5

| Mã | Quyết định đã chốt |
| --- | --- |
| D1 | `guaranteed_date`, giờ VN, hết ngày 23:59:59; không thay bằng ETA. |
| D2 | Exception chỉ lost/damaged/return_failed; at_risk khi ETA qua ngày cam kết; watch đứng yên 2 tick; slow_safe chậm chặng nhưng kịp ngày. Giữ thứ tự 8 nhãn. |
| D3 | Feed stale quá 30 phút theo timestamp nguồn, không theo giờ replay; heartbeat A3 thiếu thì chặn A1; giữ ngưỡng heartbeat 60 phút. |
| D4 | Khách tự đòi text trong chat A1 mở mới xét xu; voice không cấp. Giữ điều kiện trễ ≥2 ngày, không lỗi khách/bất khả kháng, một lần mỗi đơn. |
| D5 | DB bất biến, cursor scan ingested_at; state mới tách riêng, không sửa DB. |

Chi tiết: [decisions.md](decisions.md). Kết quả kiểm dữ liệu: [data_audit.md](data_audit.md).
