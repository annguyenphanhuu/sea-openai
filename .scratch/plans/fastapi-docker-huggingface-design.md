# FastAPI + Docker + Hugging Face Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đưa frontend hiện có và API nghiệp vụ thật lên Docker Space, có tài khoản giám khảo, replay nguồn read-only, state bền qua restart và web voice thật.

**Architecture:** Một reverse proxy :7860 định tuyến Next.js :3000 và FastAPI :8000; FastAPI lifespan sở hữu một runtime và một coordinator A3 → A2 → A1. State nghiệp vụ nằm trong một Turso database qua HTTPS, truy cập qua các storage port theo thao tác nghiệp vụ; local SQLite chỉ phục vụ dev/test. Lease và fencing bảo vệ tick/dispatch, gateway bảo vệ effects/idempotency, authorization kiểm trên từng object và lần poll.

**Tech Stack:** Python 3.11+, FastAPI/Pydantic/Uvicorn, HTTPS database client, Argon2 password hashing, pytest/httpx, Next.js hiện có, Playwright, nginx, Python process supervisor, Docker multi-stage; pin dependencies sau compatibility probe.

**Spec:** [fastapi-docker-huggingface-design.md](../specs/fastapi-docker-huggingface-design.md). Đọc cả spec và plan khi thực thi. Đây là kế hoạch, chưa triển khai hoặc xác nhận dịch vụ ngoài.

## Execution checkpoint — 2026-10-31

Task1a probe tooling và Task2 local ports đã triển khai, qua task review và scoped re-review. Task1b live compatibility **BLOCKED** vì chưa có Turso DB/token; Tasks3–13 chưa triển khai. Xem [execution checkpoint](../research/fastapi-docker-huggingface-execution.md) để biết commits, test evidence, deploy inspection và quyết định. Remote adapters không được coi là hoàn tất bằng local tests.

## Global Constraints

- “Uvicorn đúng một process, không reload”; worker logic cùng event loop, không tạo CareRuntime thứ hai.
- “Container chạy non-root UID 1000”; chỉ proxy bind `0.0.0.0:7860`, backend bind loopback.
- “Đĩa Space là ephemeral”; không fallback từ remote DB sang local SQLite, không embedded replica làm đường commit chính.
- “Tick nghiệp vụ 30 phút”; replay theo `ingested_at`, hết nhóm cùng timestamp mới checkpoint; không chạy bù theo wall clock sau wake.
- “wire datetime UTC ISO 8601”; guaranteed date và mốc 23:59:59 theo `Asia/Ho_Chi_Minh`.
- “hết hạn sau 8 giờ”; cookie `Secure/HttpOnly/SameSite=Lax`; không tự đăng ký hoặc tự nâng quyền.
- “limit mặc định 25/tối đa 100”; “giới hạn text 4000 ký tự, tiền int VND”; schema strict, cấm fields quyền/source/action tự khai.
- “Polling mặc định 2 giây lúc đang chờ, backoff khi idle”; 202 chỉ khi command/outbox đã lưu bền.
- “thiếu/quá 60 phút” heartbeat hoặc feed stale “quá 30 phút” chặn proactive; A3 chỉ siết controls.
- “giới hạn thời lượng 5 phút mỗi phiên mặc định”; voice chỉ web, transcript không đủ quyền nhận xu.
- “Retention mặc định đề xuất 30 ngày sau đợt chấm”; log hạ tầng không chứa transcript/token/PII.
- Không ghi DB nguồn, sinh world data, tải truth/heldout, cài hooks hoặc commit `.env`, DB, `data/`, `runs/`, `truth/`.
- Không sửa ownership của team: Trúc sở hữu HTTP/auth/A1/UI; An Nguyen sở hữu A2; Huy sở hữu platform/contracts/dependencies/root config/docs. Acceptance folders vẫn theo AGENTS.md, không làm yếu test của owner khác.

## Review Focus

1. Cookie hết hạn hoặc quyền bị thu hồi giữa các lần poll/voice negotiation: kiểm lại authorization, không tiếp tục lộ dữ liệu (Tasks 5, 10).
2. Cursor từ run/checkpoint/filter khác hoặc order có sort key trùng nhau: reject cursor sai scope, snapshot ổn định không thiếu/trùng đơn (Task 6).
3. HTTP timeout sau DB commit hoặc process chết sau submit trước receipt: tra cùng key, giữ unknown outcome, không double grant (Tasks 3, 8, 13).
4. Hai container chồng lấn và lease hết hạn trong lúc network request đang chạy: stale token không commit/claim; gateway vẫn deduplicate effect đã gửi (Tasks 4, 8).
5. Mic bị từ chối, provider rớt mạng hoặc browser mất kết nối: kết thúc có outcome/handoff bền, không giả call thành công hoặc đổi voice thành text (Task 10).

## Phạm vi, ownership và thứ tự

Đây là một plan tích hợp vì persistence, authorization, replay và gateway cùng bảo vệ một transaction model. Các chặng có thể bàn giao riêng: storage (1–3), replay/runtime (4), HTTP (5–9), voice/UI (10–11), deployment/acceptance (12–13). Không tuyên bố hoàn thành toàn bộ khi chỉ một chặng xanh.

Phát hiện khi đọc repo: CodeGraph hiện chỉ có 27 file, thiếu A1/platform/A2; đã bổ sung bằng các file cụ thể. `CareApi.handle(operation, payload, ctx)` có schema nội bộ và lỗi dạng chuỗi; `CareRuntime.start(...)` đang mở `MemoryStore` local và worker riêng. `SqliteEffectGateway` đã có submit/lookup thật, giới hạn effect kinds; `execute_action`/`StateStore` hiện là sync và transaction local. `QuestionStore` nhận SQLite connection và caller sở hữu transaction. Không coi những lớp này là adapter remote sẵn có.

**Xung đột cần giải quyết lúc execution:** `.scratch/plans/2026-10-31-space-storage-amendment.md` ghi quyết định Huy dùng ephemeral SQLite và chấp nhận reset. Spec được chỉ định ở đây yêu cầu Turso bền qua restart. Plan đi theo spec mới, nhưng Task 1 phải có owner Huy xác nhận thay đổi quyết định trước khi đổi shared storage/dependencies. Không tự diễn giải yêu cầu viết plan thành quyền sửa folder người khác.

Plan này chỉ tạo tài liệu `.scratch/plans/`; không fetch/merge/push trong bước viết tài liệu để tránh trộn spec đang untracked. Khi bắt đầu implementation, fetch team remote, merge main vào feature branch đúng owner, chạy baseline; mỗi đơn vị hoàn tất được commit/push sau khi kiểm tra. Không stage spec untracked hoặc thay đổi của người khác ngoài phạm vi đã giao.

## Bản đồ file và giao diện chung

| Vùng | File mới/chỉnh | Trách nhiệm |
| --- | --- | --- |
| Storage shared, Huy | `platform_huy/storage/{types,remote,migrations,commands,identity,queries,lease,backup}.py`, `platform_huy/storage/__init__.py`, `platform_huy/migrations/002_service.sql` | Database transactions, durable commands/auth/query state, lease, backup; giữ nguyên migration 001 |
| Care, Trúc | `care_truc/{storage_port,local_store}.py`, adapter remote sau compatibility gate; sửa `store.py`, `effect_store.py`, `harness.py`, `dispatcher.py`, `lifecycle.py` | Port theo request/turn/effect/recovery; bỏ truy cập SQL trực tiếp khỏi orchestration |
| A2, An Nguyen | `logistics_an_nguyen/question_port.py`, `question_remote.py`; sửa `questions.py` | Lưu/đọc/trả lời supervisor question qua port, không đổi semantics assessment |
| Platform, Huy | `platform_huy/{source_cache,coordinator,context_adapter,dispatch_gate,remote_executor,remote_effect_gateway,review_service}.py`; sửa `state_store.py`, `effect_gateway.py` khi cần seam chung | Replay, trusted facts/evidence, gate, executor/receipt và review/cancel thật trong namespace đánh giá |
| HTTP, Trúc | `care_truc/http/{__init__,app,settings,schemas,errors,security,dependencies,auth,orders,chats,cancel_review,supervisor,guard,replay,voice}.py` | App factory, auth, strict transport schemas, routes |
| Voice, Trúc | `care_truc/voice/{__init__,ports,service,provider}.py` | Session, provider adapter và channel-safe transcript |
| Frontend, Trúc | sửa `frontend/src/lib/api.ts`, `components/{app-provider,operations,order-list,order-workspace,shell}.tsx`; thêm `lib/service-schemas.ts`, `components/{login,chat-panel,voice-panel,review-panel,admin-panel}.tsx` | API thật, role-specific flows, pending/receipt và capability states |
| Deploy, Huy phối hợp Trúc | `Dockerfile`, `.dockerignore`, `compose.yaml`, `.env.example`, `deploy/{nginx.conf,supervise.py}`, sửa `README.md`, `frontend/next.config.ts`, `.github/workflows/checks.yml`, `requirements/{runtime,dev}.txt` | Image, proxy, lifecycle, CI; `docs/huggingface-runbook.md` |
| Verification | `care_truc/tests/test_http_*.py`, `test_storage_ports.py`, `test_voice.py`; `acceptance_huy/test_service_*.py`, `acceptance_an_nguyen/test_question_remote.py`, `acceptance_truc/test_service_e2e.py`; `frontend/tests/service.spec.ts`; `scripts/{probe_remote_storage,smoke_service,restore_service,load_service}.py` | Unit/integration/real deployment proof; owner tương ứng thực hiện |

Chữ ký dưới đây là **giao diện dự kiến**, không phải symbol hiện có. DTO nội bộ mới đặt trong `platform_huy/storage/types.py`, không sửa contracts shared để phục vụ HTTP. `Principal`, `CommandScope`, `CommandReceipt`, `Lease`, `TickReceipt`, `Page`, `RunView`, `VoiceSessionView` là dataclass frozen; HTTP serialize bằng schemas riêng. `CommandScope` gồm principal_id/run_id/operation/key; `CommandReceipt` gồm job_id/state/result/resource_id; `Lease` gồm owner/token/expires_at. Mọi async I/O có deadline operational monotonic. Không giữ remote transaction mở qua lời gọi model/provider.

### Task 1: Chốt preflight và chứng minh remote storage dùng được

**Owner:** Huy; Trúc cung cấp call-site requirements, An Nguyen cung cấp QuestionStore SQL.
**Files:** Create `scripts/probe_remote_storage.py`, `acceptance_huy/test_service_storage.py`, `.scratch/research/fastapi-docker-huggingface-storage.md`; modify `requirements/runtime.txt`, `requirements/dev.txt` sau probe.
**Interfaces:** Produces `probe(database_url: str, token: str) -> dict` và báo cáo compatibility có engine/driver/version/transaction limitations, không in token.

- [ ] Xác nhận quyết định persistence mới với Huy; ghi dependency approvals và điều kiện tài khoản HF/DB. Không tích hợp remote trước khi chốt. Kiểm tài liệu chính thức HF/Turso/FastAPI tại ngày execution để chọn driver HTTPS có transaction thực, Python 3.11+ và pin phiên bản; không suy khả năng từ SQLite.
- [ ] Viết test probe trên database thử tách biệt: migration chạy hai lần không đổi dữ liệu; FK/CHECK/UNIQUE bị vi phạm đều reject; transaction rollback không để lại row; hai insert cùng key chỉ một commit; CAS expected_version chỉ một winner. Thêm fault injection ngắt response sau COMMIT và đọc lại receipt bằng connection mới.
- [ ] Chạy `pytest -q acceptance_huy/test_service_storage.py`; trước adapter kỳ vọng FAIL do thiếu implementation, không phải lỗi credential. Sau đó chạy `python -m scripts.probe_remote_storage` với credentials qua env; ghi PASS/FAIL từng khả năng và restart proof vào research note. Không xem skipped network test là PASS.
- [ ] Chọn HTTP client async với transaction session được engine bảo đảm; nếu chỉ có SDK sync, dùng executor thread cố định sở hữu toàn bộ connection/transaction. Đo responsiveness bằng test heartbeat event-loop trong khi DB request bị trì hoãn. Nếu transaction không đủ mạnh, dừng Task 2–3 và sửa thiết kế; không fallback local.
- [ ] Huy pin dependencies đã thử, chạy `python -c "import contracts"` và `pytest -q`; commit `test: prove remote storage compatibility` và push feature branch sau sync team main.

### Task 2: Tạo storage ports và loại SQL khỏi orchestration care/A2

**Scope đã chốt:** local ports/adapter hoàn tất; remote files/parity tests chuyển sang Task3 sau live gate.
**Owner:** Trúc cho care; An Nguyen cho A2; Huy cho shared persistence.
**Files:** care storage files trong bản đồ; sửa `care_truc/{harness,dispatcher,lifecycle,store,effect_store}.py`; A2 `question_port.py`, `question_remote.py`, `questions.py`; create `care_truc/tests/test_storage_ports.py`, `acceptance_an_nguyen/test_question_port.py`.
**Interfaces:** `CareStore` cung cấp async operations cho begin/commit turn, load session, request lookup, recovery list, claim/record effects, confirmation consume và health; dùng DTO hiện có `SessionState`, `CustomerEvent`, `PolicyOutcome`, `Receipt`. `QuestionRepository.save(questions)`, `.list_questions(order_id=None,status=None)`, `.answer(question_id, *, answer_text, answered_by, answered_at)` là async. Port giữ nguyên tên/arguments nghiệp vụ của store cũ khi có, thêm keyword `deadline: float` cho I/O; `commit_turn` giữ expected_version và attempt token hiện có.

- [x] Viết contract tests chạy cùng bộ case cho local port: stale session version/attempt không commit; duplicate message giữ một kết quả; request+outbox commit cùng transaction; recovery không đổi principal/channel; question answer lặp cùng nội dung là idempotent, đổi nội dung conflict. Assertions: `count_requests == 1`, `count_effects == 1`, `stale_commit is False`, `answer_conflict.code == 'conflict'`.
- [x] Chạy `pytest -q care_truc/tests/test_storage_ports.py acceptance_an_nguyen/test_question_port.py`; kỳ vọng FAIL vì chưa có port.
- [x] Implement local adapter bọc logic hiện có; chuyển các direct `.db/.conn.execute` trong orchestration thành operation có tên, await port tại đúng boundaries. Không giả remote bằng sqlite connection. Inventory và ghi rõ mọi operation đang dùng vào port, không thêm CRUD tổng quát cho route.
- [x] `CareRuntime.start` nhận injected store và `background=False` cho integrated coordinator; giữ đường local dev tương thích. Chỉ integrated app dùng một coordinator, không đồng thời bật `_work()` cũ.
- [x] Chạy `pytest -q care_truc/tests acceptance_an_nguyen`; tất cả tests cũ và contract tests PASS; commit `refactor: isolate care and question persistence ports` theo từng owner, push các unit đã xác minh.

### Task 3: Remote migrations, atomic commands, sessions và recovery

**Owner:** Huy cho shared DB, Trúc cho remote care adapter, An Nguyen cho remote question adapter.
**Files:** `platform_huy/storage/{types,remote,migrations,commands,identity,queries}.py`, `platform_huy/migrations/002_service.sql`, remote care/A2 files; tests Task 1–2 mở rộng.
**Interfaces:** `Commands.accept(scope: CommandScope, payload_hash: str, payload: dict, *, deadline: float) -> CommandReceipt`; `Commands.get(scope, *, deadline) -> CommandReceipt | None`; `Identity.authenticate(token_hash: str, *, now: datetime, deadline: float) -> Principal | None`. Remote care implements Task 2 port. Storage errors phân loại `unavailable`, `conflict`, `unknown_commit`; không catch bằng sqlite3 errors.

- [ ] Viết remote tests: 20 request đồng thời cùng scope/hash trả cùng job; hash khác trả conflict; accept trả về sau khi request/outbox đã durable; response mất sau commit rồi retry trả job cũ. Khởi động client mới thấy account/session/chat/checkpoint/effects. Scope khác principal/run/operation không va key; entitlement cùng dataset/order giữa hai run vẫn chỉ một grant.
- [ ] Chạy `pytest -q acceptance_huy/test_service_storage.py care_truc/tests/test_storage_ports.py` với remote integration config; kỳ vọng FAIL cho adapter chưa có.
- [ ] Thêm migration append-only và migration version/checksum với lease; namespace `identity_`, `service_`, `care_`, `platform_`, `a2_`; bao phủ accounts/sessions/ownership, runs/ticks/assessments/A3/feeds/controls/incidents, care requests/decisions/messages/effects/receipts, questions/reviews/outbox/ledger/lease. Bỏ mô hình singleton run trong schema mới bằng run scope, không sửa migration lịch sử. Unique grant `(dataset_identity, order_id, entitlement_kind)` trong evaluation namespace; coins một lần/order, kể cả đổi run.
- [ ] Implement remote adapters bằng transaction primitives đã probe. Một durable command envelope ánh xạ duy nhất sang request_id/message_id của CareApi; không hai retry loops. Recovery chỉ lookup key cũ; unknown effect không tra được chuyển `needs_reconciliation`. Log loại lỗi và request ID, không SQL/token/payload.
- [ ] Chạy contract suite trên cả local và remote thật, reconnect/restart tests PASS; backup trước migration thử và xác minh restore test DB. Commit `feat: persist service commands and state remotely` theo owner.

### Task 4: Source cache, coordinator, lease và committed time

**Owner:** Huy; An Nguyen kiểm A2 adapter; Trúc nối runtime.
**Files:** `platform_huy/{source_cache,coordinator,context_adapter,dispatch_gate}.py`, `platform_huy/storage/lease.py`; sửa `care_truc/lifecycle.py`; create `acceptance_huy/test_service_replay.py`.
**Interfaces:** `SourceCache.ensure(*, deadline: float) -> SourceIdentity`; `Coordinator.tick(run_id: str, *, expected_checkpoint: int, deadline: float) -> TickReceipt`; `.set_schedule(run_id: str, *, mode: str, speed: float) -> RunView`; `LeaseStore.acquire(owner: str, *, now: datetime, ttl_seconds: int) -> Lease | None`, `.renew(lease, *, now) -> Lease | None`. Token kiểm lại transactionally trong tick commit và dispatch claim. Context adapter implements `ContextProvider`; gate implements `DispatchGate` hiện có.

- [ ] Viết tests: hash/schema/download sai → ready false, business mutation blocked; nguồn mở ro và hash trước/sau bằng nhau; cùng timestamp không split checkpoint; tick gọi A3,A2,A1 đúng thứ tự; future ingestion không lọt. Test 23:59:59/+07 và giây đầu ngày sau giữ semantics lateness.
- [ ] Thêm race tests hai coordinator: token tăng, chỉ một owner commit; owner cũ không claim dispatch sau takeover; checkpoint tăng đúng một lần. Sau sleep/restart không catch up, không tạo heartbeat giả. Feed 30 phút và heartbeat 60 phút vẫn theo boundary spec; lớn hơn boundary chặn.
- [ ] Chạy `pytest -q acceptance_huy/test_service_replay.py`; kỳ vọng FAIL, rồi implement download private revision/SHA256 vào rebuildable cache, không nhận filesystem path từ request. Tái sử dụng source reader/A2 `evaluate_tick` và serializer hiện có, lưu snapshot/assessment/evidence/clock/checkpoint dưới fenced transaction; A1 chỉ nhận contact từ committed tick/outbox.
- [ ] Integrated lifespan start store/source/runtime/coordinator theo dependency order, shutdown stop intake → drain/cancel có hạn → close. Auto mode là opt-in của admin và có speed hiển thị; manual mặc định. Dispatch cũng dùng fencing; controls supervisor không vượt hard gate.
- [ ] Chạy replay tests cùng `pytest -q care_truc/tests`; PASS; commit `feat: coordinate fenced replay ticks with trusted context`.

### Task 5: FastAPI factory, session auth và authorization

**Owner:** Trúc; Huy giao Identity repository và dependencies đã pin.
**Files:** `care_truc/http/{__init__,app,settings,schemas,errors,security,dependencies,auth}.py`; create `care_truc/tests/test_http_auth.py`.
**Interfaces:** `create_app(settings: Settings, services: ServiceBundle) -> FastAPI`; `require_principal(request: Request) -> Principal`; `authorize_object(principal: Principal, kind: str, object_id: str) -> None`; `trusted_context(principal: Principal) -> TrustedRequestContext`. `ServiceBundle` trong `dependencies.py` chứa identity/commands/queries/coordinator/care/gateway/voice, không global connection.

- [ ] Viết httpx ASGI lifespan tests: protected OpenAPI/docs 401; login cookie flags đúng, TTL 8 giờ, rotate; logout/revoke/expiry trả 401 kể cả lần poll sau; bootstrap secret dùng một lần; không signup. Sai Origin hoặc thiếu CSRF mutation trả 403; login kiểm Origin và cấp session-bound CSRF cho các mutation sau. Login/chat/voice bị giới hạn trả 429 kèm Retry-After.
- [ ] Test role matrix: customer/shop chỉ ownership đã xác minh; judge dashboard masked + customer assignment server-side, không review tiền/controls/replay; staff transcript cần capability riêng; reviewer/supervisor/admin có đúng capability. Fields `principal_id`, `role`, `source`, `proactive`, `Action` client tự thêm trả 422. Object ngoài scope trả 404.
- [ ] Chạy `pytest -q care_truc/tests/test_http_auth.py`; kỳ vọng FAIL do app chưa có; implement Argon2, random session lưu hash remote, bootstrap atomically, account invite/admin GET/POST/PATCH, server-selected run, CSRF token trong `/auth/me`. Rate/concurrency counters durable/shared để restart không reset protection.
- [ ] Error envelope chính xác `{error:{code,message,request_id,retryable}}` cho validation/domain/unexpected errors, không stack trace. Live chỉ process; ready kiểm DB/source/runtime; capabilities phân biệt optional provider/gateway thiếu. Chỉ tin forwarded headers từ loopback proxy và validate configured PUBLIC_ORIGIN.
- [ ] Chạy auth tests PASS; commit `feat: add authenticated FastAPI service boundary`.

### Task 6: Orders, customer/shop projections và cursor

**Owner:** Trúc; An Nguyen cung cấp metadata/serializer, Huy query store.
**Files:** `care_truc/http/orders.py`, `platform_huy/storage/queries.py`; create `care_truc/tests/test_http_orders.py`.
**Interfaces:** `Queries.orders(principal: Principal, *, run_id: str, cursor: str | None, limit: int, filters: dict) -> Page`; `.order(principal, *, run_id, order_id) -> dict`; payload assessment dùng `assessment_payload` hiện có. Cursor gắn run/checkpoint/filter/sort và last stable key.

- [ ] Tests HTTP GET `/orders`, `/{id}`, `/{id}/assessment`, `/{id}/actions`, `/customer/orders`, `/shop/orders`: limit default 25/max 100; unknown filter/invalid cursor 422, cursor khác scope/checkpoint 409; bằng sort key vẫn paginate đủ, không duplicate; run đổi không dùng cursor cũ. Ownership filter diễn ra trước count/page; projections che PII/audit đúng role.
- [ ] Run `pytest -q care_truc/tests/test_http_orders.py` → FAIL; implement snapshot query gắn committed checkpoint. Response có run_id/assessed_at/checkpoint_version/business_cutoff; null + reason code cho missing data; enum/fault/date từ A2, không map mất tám statuses vào bốn demo statuses.
- [ ] Resolve evidence JSON pointer trên payload nguồn trước filter/sort, lưu durable evidence ref riêng để Action dùng; test reorder không đổi ref và customer/shop không thấy internal evidence.
- [ ] Run tests PASS; commit `feat: expose authorized replay order projections`.

### Task 7: Chat, message jobs và handoff qua CareApi

**Owner:** Trúc.
**Files:** `care_truc/http/chats.py`, sửa `care_truc/api.py` chỉ cho mapping storage error khi cần; create `care_truc/tests/test_http_chats.py`.
**Interfaces:** Adapter gọi `await CareApi.handle(operation, payload, ctx)`; commands Task 3 gắn Idempotency-Key → request_id/message_id; GET `/jobs/{id}` kiểm principal/run/capability. Result định nghĩa tách `committed`, `pending_delivery`, `succeeded`, `needs_reconciliation`, không coi HTTP 200 là effect success.

- [ ] Viết tests POST `/chats`, GET/POST `/{id}/messages`, POST `/{id}/handoff`, GET `/{id}/decisions`, `/handoffs`, `/jobs/{id}`. Assertions: `same_key.job_id == original.job_id`, `different_payload.status_code == 409`, `other_judge_poll.status_code == 404`; 201 chỉ resource committed, 202 có Location/job durable, retry đã có kết quả 200.
- [ ] Test text 4000 hợp lệ/4001 reject; rules-only khi LLM mất vẫn trả lời; rephrase bịa amount/date/promise bị loại; ask-human và ba lượt abuse handoff; max_turns dùng params chung. Customer/judge không mint A1-initiated eligibility; trace cần capability và mỗi read kiểm lại quyền.
- [ ] Run `pytest -q care_truc/tests/test_http_chats.py` → FAIL; implement strict HTTP schemas và mapping lỗi CareApi sang envelope thống nhất; không sửa policy để test xanh. Check proactive gate ngay trước dispatch, không chỉ lúc enqueue.
- [ ] Run HTTP tests + `pytest -q care_truc/tests` PASS; commit `feat: mount durable care chat and handoff API`.

### Task 8: Remote gateway, cancellation/review và receipts thật

**Owner:** Huy implement executor/gateway/review; Trúc implement HTTP adapter.
**Files:** `platform_huy/{remote_executor,remote_effect_gateway,review_service}.py`, storage transaction operations; `care_truc/http/cancel_review.py`; create `acceptance_huy/test_service_execution.py`, `care_truc/tests/test_http_cancel_review.py`.
**Interfaces:** `RemoteEffectGateway.submit(proposal: EffectProposal, *, deadline: float) -> Receipt`, `.lookup(key: str, *, deadline: float) -> Receipt | None`; `ReviewService.review(action_id: str, *, decision: str, principal: Principal, scope: CommandScope, deadline: float) -> CommandReceipt`. Trusted `ServerContext` chỉ dựng server-side. `execute_action` local tiếp tục dùng cho dev; remote executor chia sẻ eligibility rules sau khi tách pure rule seam, không copy policy vào routes.

- [ ] Tests cancel prepare/confirm gắn principal/order/request, expired token reject, concurrent confirm chỉ một consume. Review queue/review cần reviewer, chống judge tự nâng quyền; accepted request khác executed result. Test platform capability chưa có trả 503 `capability_unavailable`, không ghi ledger giả.
- [ ] Tests coins: A1-initiated chat + explicit customer text + late_days >= 2 + no customer fault/force majeure + trusted evidence mới đủ; voice/customer-opened chat không đủ. `late_xu_for` chỉ quote, amount server tính; dataset/order grant lặp qua hai run vẫn bị chặn. Refund/voucher/shipping fee chỉ công bố available khi có ledger/provenance/executor phù hợp; cancellation có state effect thật trong evaluation namespace.
- [ ] Tests transaction rollback làm ledger/action-success/receipt cùng không tồn tại; crash sau submit trước persist receipt thì lookup khôi phục; response loss không resend unknown effect; gateway lookup unavailable giữ `needs_reconciliation`. Lease takeover giữa submit/receipt không tạo grant mới dù old owner bị fence khi commit local state.
- [ ] Run `pytest -q acceptance_huy/test_service_execution.py care_truc/tests/test_http_cancel_review.py` → FAIL; implement remote transaction với recheck hard gate/assessment/evidence/version và trusted authorization. Không dùng SqliteEffectGateway như remote driver, không để API tự ghi ledger. Bổ sung cancellation/reviewer operations mà gateway hiện chưa hỗ trợ; reconciliation là operation quản trị có audit, không nút retry effect mù.
- [ ] Run các tests trên DB HTTPS thật và local regression PASS; commit `feat: execute evaluation actions with durable receipts` theo owner. Nếu capability bắt buộc còn thiếu, ghi rõ blocker; không đánh dấu full scope hoàn tất.

### Task 9: Supervisor, guard/controls, replay jobs và audit

**Owner:** Trúc routes; Huy controls/replay; An Nguyen question repository.
**Files:** `care_truc/http/{supervisor,guard,replay}.py`; create `care_truc/tests/test_http_operations.py`.
**Interfaces:** Dùng QuestionRepository Task 2, Coordinator Task 4 và commands Task 3; `Queries` bổ sung authorized reads cho guard/feed/incidents/controls/runs/jobs. `update_control(key: str, value: object, *, principal: Principal, reason: str, scope: CommandScope) -> CommandReceipt` thuộc platform, A3 writer chỉ được tighten.

- [ ] Tests tất cả supervisor routes; answer ghi reviewer/time/evidence và không biến thành fact/money instruction. PATCH controls cần đúng capability + reason audit, A3 không nới, supervisor cũng không vượt feed/heartbeat hard gate. Lỗi IDOR kiểm cả list và detail.
- [ ] Tests POST/GET runs, GET run detail, POST ticks, PATCH schedule, GET jobs: admin-only mutation; concurrent ticks expected_checkpoint conflict, schedule manual mặc định, invalid speed reject, không nhận filesystem path; judge đọc dashboard không điều khiển thời gian chung. Run selection chỉ server/session authorized.
- [ ] Run `pytest -q care_truc/tests/test_http_operations.py` → FAIL; implement routes, audit mutations qua command transaction, strict filters/cursor như Task 6. HTTP body không được cấp controls/source/reviewer authority.
- [ ] Run PASS và test API route inventory so sánh method/path với bảng trong spec, tính cả `/health/*`, protected `/capabilities` và auth/admin; commit `feat: expose supervisor guard and replay operations`.

### Task 10: Web voice thật và transport có authorization

**Owner:** Trúc; Huy pin SDK sau chọn provider.
**Files:** `care_truc/voice/{__init__,ports,service,provider}.py`, `care_truc/http/voice.py`; create `care_truc/tests/test_voice.py`, `test_http_voice.py`.
**Interfaces:** `VoiceProvider.start(session_id: str, *, deadline: float) -> dict`, `.end(session_id: str, *, deadline: float) -> dict`; `VoiceService.start(principal: Principal, order_id: str, scope: CommandScope) -> VoiceSessionView`, `.end(principal, session_id, scope) -> VoiceSessionView`. Adapter hỗ trợ authenticated transport nếu cần; browser token ngắn hạn gắn session, long-lived key luôn server-side.

- [ ] Chọn provider STT/response/TTS hoặc realtime dựa credentials có sẵn và official docs tại execution; ghi provider/version/transport/timeout trong research note. Không tự mặc định một provider theo tên framework. Có credentials và real-provider smoke là điều kiện hoàn thành task.
- [ ] Tests provider absent → 503; POST start/end idempotent, max 300 giây operational clock, principal concurrency limit; calls list/detail có ownership/capability. Transcript luôn `web_voice`; phát biểu xin xu không tạo grant/action text. End, disconnect, timeout lưu call outcome/handoff bền; session revoke chặn negotiation và transport tiếp theo.
- [ ] Run `pytest -q care_truc/tests/test_voice.py care_truc/tests/test_http_voice.py` → FAIL; implement adapter và session persistence, browser permission denial reporting, cleanup session/provider trên shutdown; không lưu audio/token vào infra logs.
- [ ] Chạy tests PASS; smoke real provider qua HTTPS với mic thật: speech → transcript → response audio, reject mic, network interruption, end hai lần, kiểm call log và không có grant. Ghi outcome đã che PII; không xem fake-provider test là chứng minh voice xong. Commit `feat: integrate authenticated web voice sessions`.

### Task 11: Nối frontend API thật và đầy đủ luồng theo quyền

**Owner:** Trúc.
**Files:** frontend files trong bản đồ; `frontend/tests/service.spec.ts`, sửa `frontend/playwright.config.ts` cho actual backend webServer/env.
**Interfaces:** `api.ts` thêm `serviceFetch<T>(path: string, options: RequestInit, schema: z.ZodType<T>): Promise<T>` và typed functions tương ứng OpenAPI; gửi same-origin cookie/CSRF/Idempotency-Key. `service-schemas.ts` phản ánh DTO server, không tái dùng demo DTO làm contract thật.

- [ ] Viết Playwright tests qua FastAPI thật và DB test: hai judge login/đơn được gán/chat song song không thấy transcript nhau; reload còn message/job; polling 2 giây rồi backoff, retry dùng key cũ; lỗi API không hiển thị demo records. Tests staff transcript permission, reviewer account riêng, admin replay/schedule, supervisor answer/controls, customer cancel confirm, shop projection, voice unavailable/mic-denied/completed.
- [ ] Run `npm --prefix frontend run test:e2e -- tests/service.spec.ts` → FAIL; implement login + account role panels, order/assessment/action views, chat/handoff, review queue, supervisor/guard, run/jobs và voice controls. Loading/error/unknown receipt phân biệt, không báo đã cấp/hủy khi chỉ 202. Hiện run/cutoff/speed và thông báo evaluation không tác động đơn/tiền ngoài đời.
- [ ] Bật demo bằng explicit server config và nhãn demo; production proxy không cho `/api/demo/*` rơi vào FastAPI 404 rồi fallback. Demo thật sự tắt ở production; demo local mode định tuyến tới Next rõ ràng. Không expose token hoặc runtime secret qua NEXT_PUBLIC/build args.
- [ ] Run `npm --prefix frontend run lint`, `npm --prefix frontend run typecheck`, `npm --prefix frontend run build`, e2e trên API thật; tất cả PASS; kiểm laptop/mobile/mic HTTPS. Commit `feat: connect judge interface to live service API`.

### Task 12: Image, proxy, process lifecycle, CI và runbook

**Baseline deploy đã kiểm tra lúc execution:** `deploy/Dockerfile`, `deploy/start_space.py`, `deploy/fetch_data.py`, `deploy/README.md` đã tồn tại; cập nhật upstream `3c70fe2` chạy integrated A3/A2/A1, web inbox và presenter-key auth trên stdlib HTTP, local SQLite ephemeral. Next.js vẫn nằm ngoài image; presenter auth chưa phải per-judge ownership. Tái sử dụng downloader/validation, UID 1000 và allowlist; giữ đường demo cũ. Image service root mới vẫn cần Next/FastAPI/proxy/auth/remote persistence. Production SourceCache phải siết revision pin và hash bắt buộc vì downloader cũ mặc định main và manifest optional. Test `acceptance_huy/test_lunch_deploy.py`: 17 passed; chưa build image vì Docker daemon local chưa sẵn.

**Owner:** Huy root/deploy/docs; Trúc frontend config và service entrypoint.
**Files:** deployment files trong bản đồ, create `scripts/smoke_service.py`, `docs/huggingface-runbook.md`.
**Interfaces:** `python -m care_truc.http.app` khởi tạo Uvicorn loopback :8000 một worker; `deploy/supervise.py` là PID 1 quản lý nginx/Node/Uvicorn, forward signals/reap children, shutdown tối đa 10 giây rồi kill và exit nonzero khi child thiết yếu chết. `/health/ready` trả 503 khi dependency mandatory thiếu.

- [ ] Viết smoke script kiểm unauth 401, live 200, ready theo dependency, login/CSRF/authenticated read, pending job/receipt; kiểm process death làm container exit. CI chỉ credentials giả/unit hoặc isolated DB, không chạm shared run; job remote/voice release gate cần secrets thật riêng.
- [ ] Dockerfile multi-stage dùng `npm ci`, Next standalone và Python deps đã pin; runtime UID/GID 1000; nginx config không cần root/PID path hệ thống. Docker context allowlist bằng deny-all rồi include file cần build, exclude data/runs/truth/.git/.env/research/results và secret. Model/source tải lúc runtime; không COPY DB/fixture vào image thành nguồn thật.
- [ ] nginx routes `/api/*`, `/health/*` → FastAPI, còn lại Next; protected docs/OpenAPI đặt dưới `/api/v1`; streaming không buffer, WebSocket upgrade; đề xuất JSON body 64 KiB, read 30 giây, voice transport 330 giây, audio frame limit riêng 1 MiB nếu transport chuyển audio qua server. Test text 4000 vẫn qua proxy và oversized request bị reject bằng 413; tránh giới hạn HTTP làm hỏng voice stream.
- [ ] Compose local dùng proxy cùng topology và explicit storage mode dev, không deploy Compose lên HF. README thêm `sdk: docker`, `app_port: 7860`. `.env.example` liệt kê APP_ENV/PUBLIC_ORIGIN/source revision + hash từng DB/ACTIVE_RUN_ID/DATABASE_URL/SESSION_TTL=28800, DB/source/bootstrap/provider secret placeholders; thêm settings deadlines/lease/backup/voice rõ đơn vị, validation startup.
- [ ] Chạy `docker build -t sea-service:plan-check .`, `docker compose up -d --build`, `python -m scripts.smoke_service`; kiểm image history/context không secret/source DB, UID 1000, chỉ :7860 công khai, SIGTERM và kill từng essential process. Thêm CI baseline pytest/frontend checks/build/smoke không bypass owner tests. Commit `build: package service for Hugging Face Docker Space`.
- [ ] Runbook: điều kiện account/gói HF kiểm mới; tạo DB/Space, secrets, private source revision/hash, backup → leased migration một lần → readiness → bootstrap → judge assignments → external URL smoke. Ghi sleep/wake/manual replay, source/token rotation, rollback schema-compatible expand/contract, không auto downgrade/reset shared run. Người có quyền thực hiện mua gói/nhập secrets/provision; không commit giá trị secret.

### Task 13: Chứng minh restart, restore, isolation và toàn bộ phạm vi

**Owner:** Huy backup/runbook; các acceptance owner theo AGENTS.md; Trúc UI/voice E2E.
**Files:** `platform_huy/storage/backup.py`, `scripts/{restore_service,load_service}.py`, `acceptance_truc/test_service_e2e.py`, mở rộng acceptance platform/frontend; research output `.scratch/research/fastapi-docker-huggingface-validation.md` (không transcript/PII).
**Interfaces:** `backup(*, destination: str, deadline: float) -> dict`; `restore(*, source: str, target_database_url: str, dispatch_enabled: bool = False) -> dict`; export/purge command admin-only, audited, retention 30 ngày sau configured evaluation end. Restore không đụng nguồn/read-write production DB.

- [ ] Viết E2E release-source read-only: admin manual tick → A3 → A2 → A1 proactive contact receipt → assigned judge message → handoff/cancel reviewer → durable ledger receipt; branch stale/missing feeds, heartbeat >60, future ingestion, ngày VN. Test nguồn hash trước/sau bằng nhau, judge isolation, hết quyền giữa polling. Thiếu provider/gateway mandatory ghi FAIL/blocker, không dùng demo để qua gate.
- [ ] Run tests trước fault support → FAIL; implement backup lịch và trước migration, export/purge có audit; xóa theo retention không phá immutable entitlement tombstone/idempotency chống cấp lại. Nếu muốn xóa tombstone phải kết thúc cả evaluation namespace theo chính sách được Huy chốt, không chỉ tạo run mới.
- [ ] Trên DB HTTPS thật: stop/redeploy container sau 202; cắt network tại COMMIT; kill sau submit trước receipt; overlap hai container và lease takeover. Assert confirmed records không mất, coins count/order == 1, checkpoint không rollback, unknown outcome còn reconcile. Restore backup sang DB khác với dispatcher disabled rồi so account/session/chat/checkpoint/idempotency/ledger; không thực thi effects khi restore.
- [ ] Chạy `pytest -q` và `pytest -q care_truc/tests`; frontend lint/typecheck/build/service e2e; remote integration suite; Docker/external HTTPS smoke và real-provider mic smoke. Ghi chính xác command/commit/result, phân biệt skipped/blocked với PASS. Không cần chạy lại mọi check nếu chỉ sửa tài liệu sau kết quả đã chốt.
- [ ] Load scenario khởi điểm 10 browser sessions, đọc/chat/voice theo role assignments riêng; report read/chat/voice latency/error/queue depth, warm/cold state, hardware/provider limits và actual concurrency. Dùng skill benchmark-checklist khi đo, không suy capacity từ target 10 hoặc proxy-only response.
- [ ] Kiểm URL `hf.space` ngoài mạng local, judge login, readiness và demo isolation; backup restore/redeploy proof hoàn tất mới công bố full scope. Provision/secrets/voice credentials thiếu thì ghi rõ hạng mục chưa đạt, không tuyên bố đã deploy chỉ vì image build được.
- [ ] Commit `test: verify persistent judge service end to end`, sync team main rồi push verified feature units. PR mô tả behavior/contracts/tests/UI và các capability thực tế; merge/push main chỉ khi được yêu cầu. Bàn giao URL, account invitation qua kênh được phép, runbook và kết quả đo không chứa password/token.

## Kiểm tra bao phủ trước bàn giao plan

| Spec | Tasks |
| --- | --- |
| Topology/process/proxy/non-root | 4, 12 |
| Remote compatibility/ports/migrations/atomicity | 1–3, 8 |
| Idempotency/lease/fencing/unknown outcomes | 3–4, 7–8, 13 |
| Nguồn/time/replay/no future leakage | 4, 6, 9, 13 |
| Auth/ownership/roles/judge isolation | 5–11, 13 |
| Toàn bộ bảng API v1 và protected docs | 5–10; inventory Task 9 |
| A1 rules/rephrase/gate/cancel/review/coins | 7–8 |
| Real web voice/channel/timeouts | 10–11, 13 |
| Frontend thật, no fallback, receipts | 11 |
| Backup/restore/retention/rollback | 3, 12–13 |
| HF provisioning/secrets/CI/external smoke | 1, 12–13 |

Đã self-review: Task 2 định nghĩa port trước remote/lifespan; Task 3 định nghĩa command scope trước HTTP; Task 4 cấp trusted context/gate trước chat/gateway; Task 8 không giả khả năng gateway SQLite có sẵn; Task 10 cần real-provider proof. Năm failure modes ở Review Focus đều có test ở task sở hữu. Không có bước implementation hoặc deployment nào được thực hiện bởi tài liệu này.
