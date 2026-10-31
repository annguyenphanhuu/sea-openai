# D1–D5: mặc định cho khung hackathon

## Repository checks — 2026-10-31

- Use standard-library Git hooks: staged path/conflict/whitespace checks before commit; tracked-file checks, contract imports, and all acceptance tests before push.
- Repeat checks in GitHub Actions for pull requests and team branch pushes. Each clone installs hooks with `python scripts/install_hooks.py`; see `docs/guardrails.md` for limits and branch-rule enforcement.
- Keep the local CodeGraph index untracked. Hook setup does not push, open a PR, or change remote branch rules.
- Keep `docs/superpowers/` local. Shared absolute hooks use `post-checkout` to copy ignored files from the installing checkout into new worktrees without overwriting existing files. Normal branch switches do not copy files.

Chưa có `team_plan.md`. Các quyết định dưới đây được thiết lập từ mô tả của Huy và yêu cầu tiếp theo “bạn setup cho tôi đi”; đây không phải nội dung trích từ mục 6 của một plan có sẵn. Những lựa chọn bổ sung được ghi là **mặc định đề xuất**. Chưa có agent, API chạy thật hay hàm thực thi tiền.

## D1 — Replay, thời gian và dữ liệu nguồn

- Mỗi tick là 30 phút; thứ tự bắt buộc A3 → A2 → A1. Thời gian nghiệp vụ lấy từ tick replay, không lấy đồng hồ máy.
- Nguồn dự kiến: `data/release_main/core_14d.sqlite` và `data/release_main/ops_14d.sqlite`. Chỉ đọc, không tạo dữ liệu thế giới và không sửa DB nguồn. Hiện chưa có hai DB này trong checkout.
- Cursor nghiệp vụ là `ingested_at`. **Mặc định đề xuất:** mỗi tick đọc toàn bộ nhóm bản ghi có `previous_tick < ingested_at <= current_tick`, hoàn tất cả nhóm cùng timestamp rồi mới checkpoint. Replay lần đầu gồm các bản ghi đến tick đầu; không tự suy ra tick đầu khi chưa có dữ liệu. Không dùng event time thay cho ingestion time.
- **Mặc định đề xuất:** runtime state riêng ở `runs/state.sqlite`, schema lấy từ `contracts/schema_state.sql`. Dataclass dùng datetime có timezone; API/state dùng UTC ISO 8601, cố định sáu chữ số microsecond và hậu tố `Z`. Ngày cam kết giữ dạng `YYYY-MM-DD` theo Asia/Ho_Chi_Minh.
- Cần đọc schema nguồn khi dữ liệu được đưa vào trước khi viết adapter: tên bảng, khóa bản ghi, định dạng/timezone thực của `ingested_at` và checkpoint theo feed. Không giả định các chi tiết này trong code hiện tại.

## D2 — A2: nhãn, ngày trễ và bằng chứng

- `STATUSES` theo đúng độ ưu tiên: `exception > unknown_feed > customer_fault > late > at_risk > watch > slow_safe > on_track`. Mỗi đơn chỉ nhận nhãn đầu tiên thỏa điều kiện.
- Mốc cam kết là cuối ngày `guaranteed_date`, 23:59:59 giờ Việt Nam; vượt sang ngày kế tiếp mới trễ. Chậm vài giờ nhưng còn trong ngày cam kết không phải `late`.
- **Mặc định đề xuất:** `late_days = max(0, (reference_date_vn - guaranteed_date).days)`, với reference là tick cho đơn chưa giao và thời điểm giao thực tế có bằng chứng cho đơn đã giao. Ví dụ cam kết 01/11: ngày 02/11 là 1 ngày trễ, 03/11 là 2 ngày trễ. Không tính tiếp sau khi giao xong.
- ETA mới được phép là `None` khi thiếu bằng chứng. `reason_codes` và `evidence` cung cấp căn cứ có cấu trúc. Driver free text có thể hạ `confidence`, không đổi `fault_party`.
- Ngưỡng dùng chung: `p_contact = 0.7`, `p_watch = 0.2`. **Mặc định đề xuất:** đây là ngưỡng của `late_probability`, không phải `confidence`; đạt `p_contact` chỉ tạo ứng viên liên hệ, vẫn phải qua A3. Chưa định nghĩa thuật toán xác suất/ETA hay các predicate nhãn khi chưa có dữ liệu.
- `OrderAssessment` chứa `order_id`, `assessed_at`, `status`, `guaranteed_date`, `revised_eta`, `late_days`, `late_probability`, `confidence`, `fault_party`, `reason_codes`, `evidence`. Xác suất và confidence thuộc [0, 1]; late_days là số nguyên không âm. TypedDict `Evidence` giữ feed, bảng/ID nguồn, ingestion time, mã fact, giá trị và cờ structured. Đây là hợp đồng dữ liệu; chưa có bộ kiểm tra dữ liệu đầu vào.

## D3 — A3: kiểm tra feed và quyền liên hệ

- A3 ghi một `guard_heartbeat` mỗi tick và `feed_health` cho từng feed. Thiếu heartbeat, heartbeat quá 60 phút hoặc dữ liệu hỏng chặn A1 chủ động liên hệ.
- **Mặc định đề xuất:** thiếu/không xác định feed cần cho đơn cũng chặn liên hệ. Đúng 60 phút chưa phải “quá 60”; heartbeat ở tương lai so với tick không hợp lệ. Đo độ cũ theo thời gian replay.
- A3 chỉ siết control, không tự mở lại quyền đã chặn, không đụng tiền. **Mặc định đề xuất:** chỉ người quản lý được gỡ control sau khi review; feed hồi phục không tự gỡ khóa.
- `ContactTask` chứa `contact_id`, `order_id`, `assessment_at`, `created_at`, `channel`, `proactive`, `reason_code`, `idempotency_key`. Channel chỉ có `chat` hoặc `web_voice`.
- A1 phải được kiểm tra guard tại thời điểm gửi thực tế, kể cả task đã xếp hàng khi feed còn tốt. Luật này sẽ nằm ở platform; schema hiện tại chỉ lưu state, không tự thực thi quyền.

## D4 — A1, xác nhận và xu bù

- Rules nhận diện ý định trước; chỉ dùng LLM khi rules không chắc. Câu trả lời bắt đầu từ template và dữ kiện A2; LLM chỉ diễn đạt lại. Validator phải chặn số tiền, lời hứa hoặc ngày mới không khớp dữ liệu được duyệt.
- **Mặc định đề xuất:** INTENTS theo ưu tiên `request_human > confirm_cancel > cancel_order > request_late_xu > report_delivery_issue > ask_eta > ask_status > other`. Danh sách này là đề xuất vì yêu cầu ban đầu chỉ nêu thứ tự STATUSES. Chỉ nhận `confirm_cancel` khi có yêu cầu hủy đang chờ và xác nhận gắn đúng đơn; một câu “đồng ý” riêng lẻ không đủ.
- Hủy phải hỏi lại; xin gặp người hoặc chửi ở ba lượt thì chuyển nhân viên. **Mặc định đề xuất:** đếm lượt khách có lời chửi trong cùng phiên; `max_turns = 8` tính lượt khách và chuyển nhân viên nếu vẫn chưa giải quyết sau lượt thứ tám.
- `late_xu_for(order_value_vnd)` nhận số nguyên VND không âm, trả số xu nguyên theo công thức `min(1_000_000, max(10_000, floor(order_value_vnd * 0.05 / 1000) * 1000))`. Không dùng float; không nhận bool, số âm hay số thập phân. Giá trị 0 vẫn cho mức sàn 10.000 theo công thức; việc có đủ điều kiện cấp là kiểm tra khác.
- Chỉ cấp khi `late_days >= 2`, không lỗi khách, không bất khả kháng và khách tự đòi trong chat do A1 mở. Voice không đáp ứng điều kiện “trong chat”. **Mặc định đề xuất:** chưa rõ bên chịu lỗi thì chưa cấp tự động; chuyển review. Không tự mời khách nhận xu.
- `ledger_new` có `UNIQUE(idempotency_key)` và `UNIQUE(order_id)`; `outbox` cũng có idempotency key duy nhất. Đây là lớp bảo vệ DB cho retry và một lần mỗi đơn, chưa thay thế kiểm tra nghiệp vụ/giao dịch atomic của executor.
- `Action` chỉ mang định danh, loại yêu cầu, actor, thời gian, idempotency, contact, confirmation và evidence refs; không có trường số tiền. Trong tương lai mọi tiền phải đi qua duy nhất `platform_huy.execute_action`, lấy giá trị đơn từ dữ liệu tin cậy, tính bằng hàm thuần rồi ghi ledger theo transaction. LLM không tạo quyết định tiền; actor phải lấy từ ngữ cảnh xác thực, không tin trường actor do client gửi.
- **Mặc định đề xuất cho bảng quyền tương lai:** A1 có thể yêu cầu mở chat, web voice, hủy, chuyển người và xu; A2 chỉ assessment/câu hỏi; A3 chỉ heartbeat/feed/control siết; người quản lý review các yêu cầu. Chỉ executor được thực hiện tác động tài chính sau mọi kiểm tra. Chưa có bảng quyền chạy thật hay `execute_action` trong scaffold.

## D5 — Phân công, tích hợp và bề mặt API

- Nhánh cá nhân: Huy `huy`, An Nguyen `an-nguyen`, Truc `truc`. Mặc định chỉ commit local; yêu cầu mới của Huy cho phép push scaffold lần này lên nhánh `huy` để team lấy về. Mỗi người chỉ sửa folder và acceptance test của mình. `contracts/` và `requirements/` chỉ Huy sửa. **Mặc định đề xuất:** Huy sở hữu docs và cấu hình root dùng chung.
- Python tối thiểu 3.11; scaffold dùng standard library và pytest cho test. Framework API và nhà cung cấp web voice chưa chọn ở bước này.
- Contract v0 dùng chuỗi ID, field name dạng snake_case, enum là chuỗi như trong `types.py`, tuple thành JSON array và giá trị thiếu ETA thành null. Type hints không phải runtime validator; adapter/API tương lai phải kiểm tra enum, timezone, phạm vi số và evidence trước khi dùng.
- State có đủ `outbox`, `ledger_new`, `contact_log`, `guard_heartbeat`, `feed_health`, `incidents`, `supervisor_questions`, `controls`. `contact_log` là log phiên, bao gồm các cuộc web voice đã thực hiện. `outbox` chứa yêu cầu hủy/chuyển người chờ xử lý. Source order data vẫn ở hai DB nguồn.
- **Bề mặt API đề xuất, chưa triển khai:**

| Tính năng | API dự kiến | Chủ sở hữu |
| --- | --- | --- |
| Danh sách đơn và assessment | `GET /api/orders`, `GET /api/orders/{order_id}` | Huy tích hợp output An Nguyen |
| Hàng chờ duyệt | `GET /api/review-queue`, `POST /api/actions/{action_id}/review` | Huy |
| Yêu cầu hủy và xác nhận riêng | `POST /api/orders/{order_id}/cancel-requests`, `POST /api/cancel-requests/{request_id}/confirm` | Huy tích hợp Truc |
| Chat khách | `POST /api/chats`, `POST /api/chats/{contact_id}/messages` | Truc, Huy cung cấp route |
| Web voice và giám sát cuộc gọi | `POST /api/voice/sessions`, `GET /api/calls`, `GET /api/calls/{contact_id}` | Truc, Huy cung cấp route |
| Chuyển nhân viên | `POST /api/chats/{contact_id}/handoff`, `GET /api/handoffs` | Truc, Huy cung cấp route |
| Câu hỏi A2 và phản hồi quản lý | `GET /api/supervisor-questions`, `POST /api/supervisor-questions/{question_id}/answer` | An Nguyen, Huy cung cấp route |
| Trạng thái A3, incidents và controls | `GET /api/guard`, `GET /api/feed-health`, `GET /api/incidents`, `GET /api/controls`, `PATCH /api/controls/{control_key}` | Huy |
| App khách | `GET /api/customer/orders` và các API chat/voice/hủy theo quyền khách | Huy và Truc |
| Trang shop | `GET /api/shop/orders` và chi tiết đơn theo quyền shop | Huy và An Nguyen |

Mọi tính năng UI phải dùng API tương ứng; không gọi trực tiếp DB. Platform sẽ xác thực và giới hạn quyền theo khách/shop/nhân viên. Yêu cầu xu đi qua tin nhắn chat đủ điều kiện và executor; không có endpoint cho client tự đặt số tiền. Bề mặt API, payload và phân quyền chi tiết sẽ được chốt cùng implementation, không được coi là đã hoạt động nhờ scaffold này.
