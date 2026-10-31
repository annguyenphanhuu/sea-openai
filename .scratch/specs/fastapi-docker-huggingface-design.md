# FastAPI + Docker trên Hugging Face Spaces

Ngày: 2026-10-31. Trạng thái: bản thiết kế để duyệt, chưa triển khai.

## Mục tiêu và quyết định

Người dùng yêu cầu thiết kế toàn bộ API bằng FastAPI/Docker, triển khai công khai trên Hugging Face để nhiều giám khảo sử dụng. Chưa có server hoặc tên miền. Người dùng giao cho người thiết kế chọn phương án phù hợp.

Các lựa chọn dưới đây là đề xuất của người thiết kế: Docker Space, frontend Next.js hiện có, một FastAPI process, một worker logic trong cùng event loop, state bền trên Turso qua HTTPS, tài khoản mời riêng cho từng giám khảo. Không cần VPS hoặc tên miền riêng. Không cam kết lưu lượng khi chưa đo trên hardware được cấp.

Phạm vi bao gồm orders, assessments, customer/shop views, chat, web voice, hủy/xác nhận, review, handoff, câu hỏi supervisor, A3/feed/incidents/controls, replay và audit. Thành công là giám khảo đăng nhập, xem dữ liệu nguồn thật qua replay và thực hiện được luồng được phân quyền bằng HTTP, kể cả sau restart. Đây là ứng dụng đánh giá trên dataset, không kết nối ngân hàng hoặc hãng vận chuyển thật.

## Hiện trạng đã kiểm tra

- `care_truc/api.py`: CareApi là adapter JSON nội bộ; chưa có HTTP/auth. `lifecycle.py` sở hữu CareRuntime, SQLite, khóa process và recovery; kết nối hiện tại chỉ chạy cùng event-loop thread.
- `logistics_an_nguyen/`: có assessment, serializer danh sách, reader release, progress và QuestionStore. Tái sử dụng logic thay vì tự tính ETA/fault ở HTTP.
- `platform_huy/`: có A3 demo/sysguard, DTO, state và migration. Không suy từ README scaffold cũ rằng toàn bộ platform đã hoàn tất; cần xác minh implementation gateway và adapter khi lập kế hoạch.
- `frontend/`: Next.js đang gọi `/api/demo/*`, dùng bốn bản ghi minh họa; chưa phải giao diện dữ liệu replay thật.
- Requirements runtime hiện chỉ dùng thư viện chuẩn. Thêm dependencies và thay đổi contracts/platform/root config cần chủ sở hữu tương ứng thực hiện hoặc cho phép theo AGENTS.md.
- CodeGraph trả được cây 27 file nhưng không bao phủ các file A1/platform đang có trên đĩa. Các nhận định trên bổ sung từ file cụ thể và README, không xem index là bằng chứng toàn bộ runtime.

## Topology triển khai

Một image nhiều stage build frontend và backend; một Docker Space chạy container này.

`Browser -> HTTPS của Spaces -> reverse proxy :7860 -> Next.js :3000 hoặc FastAPI :8000`.

Proxy chuyển `/api/*`, `/health/*` tới FastAPI, còn lại tới Next.js. Uvicorn đúng một process, không reload; FastAPI lifespan tạo runtime và một tác vụ điều phối A3/A2/A1. Không khởi tạo một CareRuntime khác trong process worker riêng. Supervisor trong container chuyển SIGTERM tới các process, shutdown có hạn, và thoát nếu process thiết yếu chết để nền tảng restart. Proxy hỗ trợ streaming/WebSocket, giới hạn kích thước request và timeout theo loại route.

Docker Compose dành cho local; Hugging Face build Dockerfile, không cần chạy Compose trên Space. Chỉ proxy bind 0.0.0.0:7860; Node/FastAPI bind loopback. Container chạy non-root UID 1000. Cache/build artifacts tách khỏi runtime state. Secrets chỉ được đọc server-side lúc runtime.

## Lưu trữ bền và cạnh tranh

Đĩa Space là ephemeral. Không dùng nó làm nguồn sự thật cho chat, authorization, idempotency, ledger hoặc checkpoint. Không đặt SQLite đang hoạt động trên object-storage mount khi chưa có chứng minh locking/atomicity tương thích.

Đề xuất Turso remote database qua HTTPS 443; chọn engine/driver tương thích SQL thực tế sau một bước kiểm chứng bắt buộc. Đây là dịch vụ ngoài Hugging Face và cần tài khoản/token riêng. Không giả định driver remote là thay thế trực tiếp sqlite3. Đĩa local chỉ chứa bản tải nguồn bất biến và cache có thể dựng lại; không dùng embedded replica ghi local rồi sync sau làm đường commit chính.

Tạo storage ports ở cấp thao tác nghiệp vụ cho care, platform và QuestionStore. Adapter local SQLite phục vụ test/dev; adapter remote thực hiện transaction và ràng buộc tương đương. Không giả lập remote bằng thay `connect()` hoặc bắt chung mọi lỗi như sqlite3. Network I/O có deadline, không block event loop; nếu SDK đồng bộ thì connection/transaction thuộc một executor thread cố định, không chuyển SQLite connection giữa thread.

Trước khi nối toàn bộ nghiệp vụ, phải kiểm chứng trên database thử: migration, foreign keys/CHECK/UNIQUE, commit/rollback, concurrent duplicate requests, optimistic update, mất kết nối lúc commit và restart. Nếu engine không đáp ứng, dừng tích hợp storage và sửa thiết kế trước; tuyệt đối không âm thầm quay về ephemeral SQLite.

Các nhóm bảng cần lưu: account/session/ownership; runs/ticks/assessments/A3/feed/controls/incidents; care sessions/messages/decisions/requests/effects/receipts; questions/reviews/outbox/ledger; scheduler lease và migration version. Dùng một remote database, namespace rõ, để các bất biến cùng nghiệp vụ có thể nằm trong cùng transaction. Giữ migration lịch sử; Huy duyệt migration shared state, không sửa SQL cũ âm thầm.

Idempotency UNIQUE theo principal, run, operation và key, kèm payload hash. Cùng key khác payload trả 409. Ghi request/outbox trước khi trả accepted; ledger và action success commit nguyên tử. Sau timeout commit không xác định: tra cùng key/receipt, không tạo key mới và không tự gửi lại tác động chưa biết kết quả. Gateway không đủ khả năng lookup thì chuyển needs_reconciliation.

Một scheduler logic được bảo vệ bằng lease trong DB và fencing token tăng đơn điệu để chống hai container chồng lấn khi redeploy. Mọi tick commit/claim dispatch kiểm token hiện hành trong transaction. Tác động đã gửi ra ngoài vẫn cần gateway idempotency; lease không thay nó. Khóa OS hiện tại chỉ bảo vệ local process, không thay distributed lease. Unique order grant theo dataset identity và order_id trong namespace đánh giá; tạo run mới không cho cấp lại cùng đơn trong cùng môi trường.

Backup remote state theo lịch và trước migration; kiểm thử restore sang môi trường tách biệt, tắt dispatcher. Retention mặc định đề xuất 30 ngày sau đợt chấm; admin chủ động export/xóa bằng tác vụ có audit. Không ghi transcript/token/PII vào log hạ tầng.

## Dữ liệu nguồn và thời gian

Đưa hai DB release vào kho dữ liệu riêng được cấp quyền; tải bằng token từ Space Secrets, pin revision và SHA-256; không commit DB vào Space/repo công khai hoặc image. Nếu tải/hash/schema lỗi thì readiness báo thiếu nguồn và mutation nghiệp vụ bị chặn. Reader luôn mode=ro; kiểm hash trước/sau replay. Không tải truth/heldout.

Replay chỉ nhìn thấy dữ liệu qua ingested_at, đọc hết nhóm cùng timestamp trước checkpoint. Tick nghiệp vụ 30 phút; mặc định chạy manual cho buổi chấm, admin có thể bật auto với tốc độ hiển thị rõ. Sau sleep/restart không chạy bù đồng loạt theo đồng hồ thật. Thời gian nghiệp vụ được chốt trong committed tick; timeout/auth/lease dùng đồng hồ vận hành, tách biệt. Feed staleness so timestamp nguồn với cutoff nghiệp vụ theo D3, không đổi timestamp nguồn thành thời gian xử lý. Ngày cam kết giữ ngày VN; wire datetime UTC ISO 8601.

## Auth, phân quyền và trải nghiệm giám khảo

Không mở tự đăng ký. Bootstrap admin qua secret dùng một lần; admin tạo tài khoản mời, mật khẩu băm bằng thư viện phù hợp, session token ngẫu nhiên lưu dạng hash trong remote DB. Cookie Secure/HttpOnly/SameSite=Lax, rotate khi login, revoke khi logout, hết hạn sau 8 giờ. Mutation kiểm Origin và CSRF; rate limit login/chat/voice và hạn mức đồng thời theo principal. Ưu tiên URL hf.space trực tiếp để không phụ thuộc third-party cookie của iframe.

Vai trò: customer chỉ đọc/chat/hủy đơn được gán; shop chỉ đọc projection shop của đơn được gán; staff xem/handoff theo capability; reviewer phê duyệt; supervisor trả lời câu hỏi/controls theo capability; admin quản lý tài khoản và replay. Judge có quyền đọc dashboard đã che PII và tương tác chat dưới danh tính customer đánh giá được gán server-side, không tự impersonate qua JSON. Judge không có quyền nới controls, đổi replay chung hoặc duyệt tiền. Hành động đầy đủ của reviewer được trình diễn bằng tài khoản reviewer riêng của đội, không nút tự nâng quyền.

Mặc định dùng một run trình diễn chung, chỉ admin điều khiển thời gian; mỗi judge có session riêng và tập đơn được gán riêng để tránh thay đổi chồng chéo. Quyền staff không tự cho truy cập transcript nhạy cảm; trace/evidence có capability riêng. Kiểm quyền trên mọi object và mọi poll; chưa xác minh customer/shop ownership thì deny, không đoán từ order_id. Không đưa PII vào response công khai.

## API v1

Prefix `/api/v1`; giữ `/api/demo/*` chỉ trong demo mode được gắn nhãn, không fallback tự động khi API thật lỗi. API docs/OpenAPI được bảo vệ bằng đăng nhập. Các route mới là thiết kế, chưa phải endpoint đang chạy.

| Nhóm | Routes |
| --- | --- |
| Auth/admin | POST `/auth/login`, `/auth/logout`; GET `/auth/me`; GET/POST `/admin/users`; PATCH `/admin/users/{id}` |
| Orders | GET `/orders`, `/orders/{id}`, `/orders/{id}/assessment`, `/orders/{id}/actions` |
| Customer/shop | GET `/customer/orders`, `/shop/orders` |
| Chat | POST `/chats`; GET/POST `/chats/{id}/messages`; POST `/chats/{id}/handoff`; GET `/chats/{id}/decisions`, `/handoffs` |
| Voice/calls | POST `/voice/sessions`; POST `/voice/sessions/{id}/end`; GET `/calls`, `/calls/{id}`; authenticated transport route nếu provider cần |
| Cancel/review | POST `/orders/{id}/cancel-requests`, `/cancel-requests/{id}/confirm`; GET `/review-queue`; POST `/actions/{id}/review` |
| Supervisor | GET/POST `/supervisor-questions`; POST `/supervisor-questions/{id}/answer` |
| Guard | GET `/guard`, `/feed-health`, `/incidents`, `/controls`; PATCH `/controls/{key}` |
| Replay | POST `/runs`; GET `/runs`, `/runs/{id}`; POST `/runs/{id}/ticks`; PATCH `/runs/{id}/schedule`; GET `/jobs/{id}` |
| Health | GET `/health/live`, `/health/ready`; authenticated GET `/capabilities` |

Run hiện hành do cấu hình server/session chọn, không nhận path filesystem từ client. Payload orders lấy assessment và metadata từ A2; không sửa enum/date/fault. Evidence JSON pointer resolve trước lọc/sắp, không dùng pointer tạm làm Action.evidence_ref.

Danh sách dùng cursor ổn định, limit mặc định 25/tối đa 100, lọc allowlist. Response có run_id, assessed_at, checkpoint_version và business cutoff khi liên quan. Dữ liệu thiếu trả null/reason codes, không đoán. Projections customer/shop che audit nội bộ.

Mutation gửi Idempotency-Key; adapter ánh xạ request_id/message_id hiện có, không tạo hai cơ chế retry độc lập. JSON schema strict, từ chối fields lạ, giới hạn text 4000 ký tự, tiền int VND. Không nhận Action tùy ý, source/capabilities/proactive do client khai. 201 cho resource đã commit, 202 cho command/effect đã được ghi bền chờ xử lý và trả job/location, 200 cho đọc/kết quả đã có; HTTP accepted không đồng nghĩa đã gửi/hủy/cấp tiền. Polling mặc định 2 giây lúc đang chờ, backoff khi idle.

Lỗi thống nhất `{error: {code, message, request_id, retryable}}`; 401/403, 404 tránh lộ object, 409 conflict, 422 validation, 429 có Retry-After, 503 dependency chưa sẵn. Không lộ SQL, secrets hay stack trace. Liveness chỉ kiểm process; readiness phản ánh DB/source/runtime, capabilities thể hiện voice/model/gateway chưa sẵn. Rules-only vẫn phục vụ chat nếu LLM mất, nhưng gateway/gate/evidence thiếu phải chặn hiệu ứng.

## A1, voice và execution gate

Mount CareApi bằng TrustedRequestContext dựng sau auth; ownership ContextProvider phải đọc dữ liệu trusted tại cutoff. Rules trước LLM; text khách/tài xế là data. Validate mọi rephrase với facts/amount/date/promise. Duy trì tối đa lượt, chuyển người khi khách yêu cầu hoặc ba lượt lạm dụng. Chỉ A1 nội bộ được mở proactive contact; customer/judge POST chats không thể tự tạo eligibility A1-initiated.

Trước mỗi proactive dispatch kiểm lại heartbeat A3 (thiếu/quá 60 phút), mandatory feeds (stale quá 30 phút theo nguồn), controls và phiên bản assessment. A3 chỉ siết; chỉ supervisor đủ quyền có thể nới, có audit lý do, và không được vượt hard gate feed/heartbeat.

Hủy cần confirmation riêng gắn principal/order/request, hết hạn và chỉ consume một lần trong transaction. API review tạo trusted reviewer context, gọi gateway platform, không tự ghi ledger. Xu chỉ từ explicit customer text trong chat A1 mở, trễ từ hai ngày, không customer fault/force majeure, once-per-order. late_xu_for chỉ tính quote; executor kiểm lại và cấp quyền. Refund/voucher/shipping-fee-refund chỉ bật khi platform có lưu vết và execution capability phù hợp.

Voice chỉ web, dùng adapter STT/response/TTS hoặc realtime có timeout và browser permission; provider/SDK cụ thể giao người triển khai chọn theo khóa và khả năng sẵn có, phải có real-provider smoke test trước khi tuyên bố voice hoàn thành. Token provider lâu dài không ra browser; nếu negotiation cần browser token thì token ngắn hạn gắn session. Transcript voice luôn giữ channel=web_voice, không chuyển thành request text để nhận xu. End-session idempotent, lưu outcome/handoff/call log; giới hạn thời lượng 5 phút mỗi phiên mặc định. Thiếu provider thì 503 capability_unavailable, không giả cuộc gọi. Đây là hạng mục bắt buộc để đạt toàn bộ phạm vi, không được đánh dấu xong chỉ vì route tồn tại.

Trong môi trường chấm, hành động được thực thi vào state/ledger đánh giá tách biệt; UI ghi rõ không tác động tiền hoặc đơn hàng ngoài đời. Gateway thật ngoài môi trường này là phạm vi khác, cần credentials và authorization riêng.

## Docker, cấu hình và triển khai

Đề xuất thêm FastAPI/Uvicorn, client HTTPS database, auth hashing, HTTP test tooling theo review của Huy; pin phiên bản khi implementation. File HTTP/auth dưới care_truc, adapter A2 dưới owner An Nguyen nếu cần, platform/gate/migration dưới Huy. Không tự sửa folder người khác hoặc shared requirements theo mặc định.

Deployment assets gồm Dockerfile multi-stage, dockerignore allowlist, entrypoint/supervisor/proxy config, README metadata `sdk: docker`, `app_port: 7860`, local compose, env example không chứa secret, runbook provision/backup/restore/rollback và CI build/smoke. Root config do Huy phối hợp. Không cài hooks. Chỉ push nội dung allowlist sang Space; không mirror .git, data, runs, truth, .env hoặc fixture thành dữ liệu thật.

Biến cấu hình: APP_ENV, PUBLIC_ORIGIN, SOURCE_REPO_ID/REVISION/SHA256, ACTIVE_RUN_ID, DATABASE_URL, SESSION_TTL. Secrets: source download token, DB token, bootstrap admin secret, provider keys. Log JSON chứa request/job/run ID và reason code, không chứa token/body chat. Middleware chỉ tin forwarded headers từ proxy nội bộ.

Trình tự đưa lên HF: kiểm account tạo được Docker Space và storage DB -> tạo remote DB -> kiểm storage adapter -> tạo Space và metadata -> đặt secrets -> tải nguồn/pin hash -> build -> migration một lần dưới lease -> readiness -> bootstrap admin -> tạo judge accounts -> smoke từ URL ngoài -> gửi link. Tạo tài khoản, mua gói, nhập secrets và công bố link thật là các bước triển khai sau thiết kế; không thực hiện bằng tài liệu này.

Tài liệu HF hiện ghi Docker Space mới cần gói trả phí phù hợp; không mặc định chi phí bằng không. Tình trạng sleep phụ thuộc hardware; chọn runtime không sleep trong buổi chấm nếu khả dụng, kiểm readiness trước lịch chấm. Không dùng HTTP ping giả hoạt động để lách sleep. Khi wake, chỉ tiếp tục checkpoint đã commit sau khi giành lease và kiểm A3; không giả heartbeat mới.

## Điều kiện nghiệm thu và giới hạn

- Existing acceptance và care tests giữ nguyên ý nghĩa; HTTP integration kiểm auth/IDOR, role/ownership, strict schema, retry/conflict và mapping CareApi. Frontend e2e đi qua API thật, không demo fixture.
- End-to-end với release read-only: tick A3 -> A2 -> A1 -> message receipt/handoff/cancel review, ngày VN, không future leakage, missing/stale feeds và heartbeat chặn đúng.
- Restart sau accepted request, mất kết nối lúc commit, chết sau submit trước receipt, hai instance tranh lease: không mất dữ liệu đã xác nhận, không double grant, unknown outcome phải reconcile. Kiểm DB thật qua HTTPS, không suy từ SQLite unit test.
- Hai tài khoản judge thao tác đồng thời không đọc transcript của nhau; khác role không được nâng quyền. Khởi điểm kiểm 10 browser sessions đồng thời; đây là mục tiêu kiểm thử, không phải cam kết capacity. Đo latency/error/queue depth riêng cho đọc/chat/voice và công bố kết quả thực tế.
- Source hash không đổi; backup/restore và redeploy giữ account/session/chat/checkpoint/idempotency/ledger. Chỉ readiness xanh khi dependency bắt buộc dùng được.
- Voice real-provider test, mic HTTPS và không cấp xu từ transcript. Nếu chưa tích hợp voice/gateway thì ghi đúng phần còn thiếu, chưa đạt phạm vi tất cả.
- Rollback image phải tương thích schema; dùng migration expand/contract phù hợp, không auto downgrade destructive. Không reset shared run để sửa lỗi.

## Các lựa chọn còn giao người triển khai

Tên Space/organization, khu vực remote DB phù hợp, driver/engine sau compatibility check, provider voice/LLM theo credentials, chi tiết namespace/schema indexes, thư viện session hashing và proxy/supervisor cụ thể. Không giao lại các quyết định về persistence, authorization, D1-D5 hay semantics idempotency cho mặc định thư viện.

## Nguồn tham khảo chính thức

- HF Docker/ports: https://huggingface.co/docs/hub/spaces-sdks-docker
- HF visibility/secrets/network/sleep/account requirements: https://huggingface.co/docs/hub/spaces-overview
- HF ephemeral disk/volumes: https://huggingface.co/docs/hub/main/spaces-storage
- Turso Python remote drivers: https://docs.turso.tech/sdk/python/quickstart
- Turso SQL over HTTPS: https://docs.turso.tech/sdk/http/reference
- FastAPI Docker deployment: https://fastapi.tiangolo.com/deployment/docker/

Chỉ tài liệu được tạo trong bước này. Chưa có API, image hoặc Space được triển khai.
