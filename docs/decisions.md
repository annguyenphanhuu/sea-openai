# Quyết định D1–D5

Huy chốt các quyết định này ngày 31/10/2026; chúng thay thế các mặc định trước đây. Xem mục 6 của [team_plan.md](team_plan.md). Đây là đặc tả, chưa phải logic agent đã triển khai.

## Repository checks — 2026-10-31

- Use standard-library Git hooks: staged path/conflict/whitespace checks before commit; tracked-file checks, contract imports, and all acceptance tests before push.
- Repeat checks in GitHub Actions for pull requests and team branch pushes. Each clone installs hooks with `python scripts/install_hooks.py`; see `docs/guardrails.md` for limits and branch-rule enforcement.
- Keep the local CodeGraph index untracked. Hook setup does not push, open a PR, or change remote branch rules.
- Keep `docs/superpowers/` local. Shared absolute hooks use `post-checkout` to copy ignored files from the installing checkout into new worktrees without overwriting existing files. Normal branch switches do not copy files.

## D1 — Ngày cam kết

Lấy duy nhất `orders.guaranteed_date`, múi giờ `Asia/Ho_Chi_Minh`, hết ngày lúc **23:59:59**. Không dùng `promised_at`, `estimated_date` hoặc ETA mới thay ngày cam kết. Chậm vài giờ trong cùng ngày không phải trễ ngày. Thiếu ngày cam kết phải báo thiếu dữ liệu, không tự lấy ETA thay.

## D2 — Nhãn của A2

Mỗi đơn đúng một nhãn theo thứ tự:

`exception > unknown_feed > customer_fault > late > at_risk > watch > slow_safe > on_track`

- `exception` chỉ từ trạng thái `lost`, `damaged`, `return_failed`; không tự coi `waiting_to_return`, `failed`, `returning` là exception.
- `unknown_feed`: thiếu độ tin cậy của feed cần thiết theo A3.
- `customer_fault`: bằng chứng có cấu trúc về lỗi khách. Chữ tài xế chỉ hạ độ tin, không đổi bên chịu lỗi.
- `late`: đã lỡ ngày cam kết theo D1, sau khi xét các nhãn ưu tiên cao hơn.
- `at_risk`: ETA qua ngày cam kết, không chỉ chậm vài giờ trong ngày.
- `watch`: đứng yên hai tick liên tiếp, mỗi tick 30 phút.
- `slow_safe`: chậm chặng nhưng dự kiến vẫn kịp ngày cam kết.
- `on_track`: không thỏa các nhãn trước.

A2 xuất ETA, nguyên nhân và bằng chứng; không đụng tiền. Reason code cần được kiểm cùng bằng chứng cấu trúc, ví dụ `customer_unreachable` nhưng `call_attempts=0` không đủ để tự quy lỗi khách.

## D3 — Feed stale và heartbeat

Feed stale khi quá **30 phút theo timestamp nguồn**, không theo giờ replay. Không lấy thời điểm xử lý/tick làm timestamp mới cho dữ liệu cũ. Lưu riêng `feed_health.source_timestamp` và `last_ingested_at`: timestamp sự kiện và timestamp nhận dữ liệu khác nhau. Ví dụ nguồn có `scan_events.event_at`, telemetry có `metrics.ts`; adapter phải ghi rõ timestamp nguồn của từng feed.

Feed status chỉ gồm `trusted`, `stale`, `corrupt`, `missing`. A3 ghi heartbeat mỗi tick, có `agent_id`. **Thiếu heartbeat A3 thì chặn A1 chủ động liên hệ**; giữ ngưỡng heartbeat quá 60 phút cũng chặn theo yêu cầu trước. Feed stale/corrupt/missing không được dùng để cho phép chủ động liên hệ. A3 chỉ siết, không tự nới và không đụng tiền.

Không đồng nhất việc một đơn không có scan mới với feed bị hỏng. Freshness phải xét cấp feed cùng timestamp nguồn và bằng chứng telemetry; `checked_at` chỉ là thời gian audit. Chưa có phép tính stale chạy thật trong scaffold.

## D4 — Điều kiện cấp xu

Chỉ xét xu khi **khách tự đòi bằng text trong chat do A1 mở**. Voice không cấp xu; transcript voice và ticket lịch sử không tự trở thành yêu cầu text hợp lệ trong phiên đó.

Giữ các điều kiện đã chốt: trễ từ hai ngày, không lỗi khách, không bất khả kháng, một lần mỗi đơn. `late_xu_for(items_value_vnd)` tính 5%, làm tròn xuống nghìn, sàn 10.000, trần 1.000.000; `None` hoặc 0 trả 10.000. Đây chỉ là hàm tính, không quyết eligibility.

Mọi tiền qua duy nhất `platform_huy.execute_action` trong implementation tương lai. LLM không tính hay quyết số tiền. `Action.amount_vnd` do logic xác định tạo ra; executor kiểm lại số tiền, nguồn, bằng chứng, phê duyệt và idempotency. `ALLOWED_SOURCES` là ma trận chung; `shipping_fee_refund` chỉ từ `cancel_reviewer`.

## D5 — DB bất biến và cursor

Phát lại `data/release_main/core_14d.sqlite` và `ops_14d.sqlite`; không sinh world data, không sửa DB nguồn, kể cả `sim_clock`, index hay ledger. Mở SQLite URI `mode=ro`; state mới ở `runs/`, áp dụng `contracts/schema_state.sql`.

Cursor scan là **`scan_events.ingested_at`**, không đổi sang `event_at`. Đọc trọn nhóm cùng timestamp trước khi checkpoint; dữ liệu có nhóm đến 12 dòng cùng mốc. Dùng `event_at` sắp tiến trình đã được nhìn thấy, không để đọc trước scan chưa nhận.

DB chứa tương lai đến 08/11/2026. Adapter phải lọc as-of và che trường tương lai bằng tham số; không cập nhật `sim_clock` nguồn để dùng view có sẵn. Các bảng không có `ingested_at` phải ánh xạ timestamp có thật (`ts`, `received_at`, `created_at`, `attempt_at`, `reported_at`...) ở adapter, không thêm cột hay đổi cursor scan. Quyền thấy dữ liệu as-of và freshness D3 là hai kiểm tra riêng.
