# Handover 13:00 — 31/10/2026

Hoàn tất lượt lunch lúc khoảng 12:39 VN và dừng theo yêu cầu. Chỉ commit local trên `huy`; không push, không merge main. Main giữ `77a601e`, remote Huy giữ `824f189` tại lần fetch của lượt này.

## Đã làm theo thứ tự mới

1. `git fetch --all --prune`; merge `origin/main` và main repo team (`upstream/main`) vào Huy. Không conflict. Baseline 518 test đạt.
2. MongoDB đã revert từ lượt trước; giữ SQLite-only.
3. `6dd2652`: `money.py` có `execute_action`/`get_receipt`, interface `StateStore`, duy nhất `SqliteStateStore` dùng transaction/schema hiện có. Xu và voucher hai key riêng; chỉ thành công khóa key; từ chối có audit, không ghi ledger/outbox. Kiểm quyền, owner, tiền, bằng chứng, vòng đời chat và A3 hiện tại.
4. `9309df5`: Docker Python 3.11/cổng 7860, startup tải private dataset HF theo allowlist khi chưa có release; `SEA_RELEASE_DIR`, runtime local, không đóng gói data/truth/secrets. Chặn runtime alias cả core/ops, kể cả hardlink. Research: `.scratch/research/hf-space-deploy.md`.
5. Không làm MongoStateStore.
6. `b4ee32d`: `SqliteEffectGateway` nối proposal A1 đã lưu với executor thật; ánh xạ key cũ của A1 sang `xu:{order}`, giữ key/hash biên nhận phía A1, kiểm session/text/provenance và đọc lại biên nhận SQLite khi retry.

Phân công sub-agent: `lunch_money` làm executor/test; `lunch_deploy` làm deploy/test; `lunch_review` review độc lập bằng context sạch. Mỗi agent dùng worktree riêng, không commit/push. Controller tích hợp gateway và sửa các lỗi review.

## Kiểm chứng

- Python 3.11, không có PyMongo: **618 acceptance test + 96 test A1 đạt**, không skip.
- Reviewer chạy riêng **100 test lunch đạt**, chấp thuận phạm vi sau sửa bốn nhóm lỗi: binding biên nhận, quyền seller/customer, tin nhắn sau đóng chat, runtime alias DB nguồn.
- Mutation thật bỏ guard: **3 test thất bại**; khôi phục guard rồi GREEN. Các lỗi review đều có log RED trước sửa.
- Đơn release thật `261021ZS7E76FW`: guard cho phép, executor từ chối vì thiếu bằng chứng khách xin; ledger/outbox đều rỗng, hash cả hai DB không đổi. Không tạo bằng chứng giả để có ca cấp thành công.
- Launcher thật `python -m deploy.start_space` chạy bằng **Python 3.11.17** với release local: HTTP đạt; NEXT `12:00 → 12:30`, hash nguồn không đổi. Lần thử đầu timeout do harness chỉ chờ 1 giây; đã lưu lỗi, sửa readiness/timeout của harness và chạy lại đạt, không sửa ứng dụng để né kiểm thử.

Log local: `.scratch/runs/lunch/{baseline,review,final-default.log,final-care.log,release-money-smoke.log,space311-smoke.log}`, `.scratch/runs/lunch-money/`, `.scratch/runs/lunch-deploy/`. Research/decisions/plan đã lưu trong `.scratch`; log không đưa lên Git.

## Giới hạn cần nối tiếp

- **Chưa có producer nguồn/bằng chứng platform hoàn chỉnh và transport chat thật.** Executor mặc định từ chối nếu chưa cấu hình producer đáng tin hoặc thiếu dữ liệu. Test cấp thành công dùng fixture SQLite; không phải cấp xu cho khách thật. Gateway dùng mapping bằng chứng server, không tự tạo clearance từ chat.
- Chưa gắn gateway vào HTTP/UI đang chạy; UI Space hiện là A3 và bản nháp chăm sóc. Cancellation/refund/eta_notice chưa được executor này hỗ trợ, trả `policy_not_configured`, không giả thành công.
- A1 hiện còn ngưỡng heartbeat 60 phút, đường voucher chưa nối, và rejected receipt là terminal. Cần Trúc phối hợp để trải nghiệm xin lại sau xác minh chạy xuyên suốt; platform đã không khóa key khi từ chối.
- Docker daemon không chạy nên chưa build/chạy image. Chưa tải private HF hoặc triển khai Space thật. Cần cấu hình `SEA_DATASET_REPO` và secret runtime `HF_TOKEN`; hướng dẫn tại `deploy/README.md`. Không bịa ID hoặc dùng token trong Dockerfile.
- Runtime SQLite trên đĩa Space; restart về baseline được chấp nhận. Trong cùng run vẫn chống cấp trùng. Không có tác động lên ví Shopee thật.

Đã dừng. Không tự triển khai thêm hoặc publish.
