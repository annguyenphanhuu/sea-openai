# FastAPI Docker — execution checkpoint

Ngày: 2026-10-31. Nhánh: `truc/fastapi-docker`. Spec và plan: `.scratch/specs/fastapi-docker-huggingface-design.md`, `.scratch/plans/fastapi-docker-huggingface-design.md`.

## Trạng thái

- Task 1a: probe Turso HTTPS và offline protocol/fault tests đã qua task review và một vòng sửa/re-review; commits `647f44c`, `1c7b8dd`.
- Task 1b: **BLOCKED**. Người dùng xác nhận chưa có database/token Turso. Chưa chạy compatibility trên engine thật, chưa chứng minh hosted restart; không tích hợp remote business storage trước khi gate này đạt.
- Task 2: local async CareStore/LocalCareStore và QuestionRepository đã triển khai; giữ API sync SQLite cho tests/gateway cũ. Thêm token kiểm processing attempt ngay trong transaction, injected runtime không cần file/OS lock, explicit async health. Commit `1949315`, sửa API503 boundary `7c3ef7c`; scoped re-review đã xác nhận sửa đúng, không có Important/Critical mới.
- Tasks 3–13: chưa triển khai. Dependencies storage/runtime/HTTP tiếp theo cần Task 1b đạt. Chưa có server FastAPI, remote runtime hoặc Space mới được triển khai.

## Kiểm chứng

- Baseline đầu phiên sau sync `origin/main` tới `8f58e83`: 633 acceptance tests và 96 care tests đạt.
- Task 1a sau sửa: 15 probe tests đạt. SQLite HTTP harness chỉ kiểm tooling, không chứng minh Turso.
- Task 2 trước fix API boundary: toàn bộ care + ba acceptance folders đạt 755 tests. Fix API boundary thêm hai regression; focused API/port/question suite đạt 22 tests. Không gọi kết quả 755 là full-suite result của commit sau fix.
- Sau khi merge main mới `3c70fe2` tại `cf2e798`, chạy lại `python -m pytest -q care_truc/tests acceptance_an_nguyen acceptance_truc acceptance_huy`: **798 passed in 132.41s**, exit0. Bao gồm integration/demo/deploy mới và hai API regression sau fix. `python scripts/guardrails.py --all` và `git diff --check` đều đạt.
- Existing global pytest_asyncio fixture-loop deprecation warning đã có từ baseline.
- `git diff --check` đạt cho code task đã commit.

## Deploy hiện có đã kiểm tra theo yêu cầu bổ sung

`deploy/` đã tồn tại từ commit `9309df5`, gồm Dockerfile, Hub downloader và startup launcher cho prototype/A3. `origin/main` vừa có thêm commit `3c70fe2`: Docker bật `SEA_INTEGRATED=1`, launcher chạy `platform_huy.serve_ui --integrated` trên :7860, tích hợp A3/A2/A1 và web inbox SQLite. API dùng `LIVE_PRESENTER_KEY`/`X-Presenter-Key`, README yêu cầu Space private; đây là presenter access, chưa có tài khoản/ownership riêng từng judge. State vẫn local SQLite và README chấp nhận reset sau restart. Next.js nằm ngoài source allowlist, chưa phải FastAPI/Turso theo spec mới.

Tái sử dụng UID1000, Docker allowlist, downloader private dataset với exact paths, read-only checks, staging + rename. Cần siết revision pin và SHA256 bắt buộc vì code cũ mặc định revision main và manifest optional; cập nhật build cho frontend/service/proxy trong Task12. Giữ demo entrypoint cũ hoạt động.

`python -m pytest -q acceptance_huy/test_lunch_deploy.py`: **17 passed**. Docker CLI29.1.3 có sẵn nhưng `docker info` thất bại do Linux engine named pipe không tồn tại; chưa build/run container được. Không tìm thấy Turso configuration trong deploy.

## Điều kiện để tiếp tục tích hợp

1. Tạo database Turso thử riêng, cấu hình URL/token server-side theo `.scratch/research/fastapi-docker-huggingface-storage.md`; không gửi token qua chat hoặc Git.
2. Chạy probe có explicit isolated-test write opt-in, ghi engine/version, tất cả invariant và cleanup results; xác minh persistence/reconnect theo gate trong spec.
3. Chỉ sau khi gate đạt mới nối remote care/platform/question state (Task3), sau đó coordinator, auth/API/UI/voice/deployment. Provider credentials/HTTPS mic test và Docker daemon sẽ cần ở các task sau.

## Quyết định trong lúc triển khai

Các quyết định dưới đây giữ dấu vết để owner có thể xem và đổi lại; chưa xóa workspace SDD vì plan chưa hoàn tất.

- Ruling: Proceed with implementation across plan-owned areas in this feature worktree, deferring previous owner/persistence policy conflicts as the user explicitly instructed — avoids blocking on historical policy — cost if wrong: owners may require reverting or adapting these feature-branch changes.
- Ruling: Live external compatibility checks require actual test credentials; prepare and test tooling, but do not mark a live check passed or integrate remote business storage before proof — spec requires this gate — cost if wrong: delayed downstream integration.
- | 7, 9 | job route shared owner → replay operations | Ruling: chats owns shared GET jobs handler; operations reuses registration rather than duplicate route — avoid ambiguous routing — cost if wrong: route ownership rework. |
- Ruling: Split Task 1 into 1a probe/tooling and 1b live compatibility proof; review 1a and continue only independent local work while 1b lacks credentials — concrete code is useful without treating mock evidence as remote proof — cost if wrong: probe/port adaptation after real engine testing.
- Ruling: Task 2 implements local async ports and parity only; remote adapter files and parity tests wait for Task 3/live gate, so local question tests may be named test_question_port.py — avoids placeholder remote code and preserves the spec compatibility gate — cost if wrong: file naming/interface adaptation later.
- Ruling: Extend AttemptToken with a backward-compatible per-processing-attempt field and verify optional token atomically in turn commit — async storage introduces a yield after caller checks, so session/boot checks alone can allow stale callbacks — cost if wrong: local token API migration/rework; preserve legacy no-token callers.
- Ruling: Place local CareStore protocol in care_truc/storage_port.py and adapter in care_truc/local_store.py rather than new nested storage package — existing deploy Docker allowlist only copies care_truc/*.py, and split files preserve responsibilities without breaking it — cost if wrong: imports/file relocation at later storage integration.
