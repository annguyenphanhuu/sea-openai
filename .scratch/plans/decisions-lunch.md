# Quyết định demo buổi trưa — 31/10/2026

## Phạm vi chỉ dẫn

Huy xác nhận “bước 2” và “bước 5” là các bước trong tin nhắn, không tham chiếu tới một file kế hoạch. Không cần tìm hoặc yêu cầu đường dẫn kế hoạch. Không tự ánh xạ hai bước này sang Task 2/Task 5 của kế hoạch platform chín task cũ.

## Bước 2 — Bỏ MongoDB

- Revert PR #8 bằng `git revert -m 1 76abd17` để gỡ tích hợp MongoDB khỏi main.
- Bỏ module MongoDB, cấu hình mẫu, dependency và test dành riêng cho tích hợp đó.
- Kiểm tra import và pytest trong môi trường không cài `pymongo`.
- Giữ log audit cũ ở local, ngoài Git; không đưa lại log vào tracking khi revert.

Đã hoàn thành: revert `645d2b3`, cập nhật quyết định `77a601e`; cả hai đã có trên `upstream/main` và `upstream/huy`. Kiểm thử môi trường sạch: `import contracts` đạt, xác nhận không có `pymongo`, 518 acceptance test và 96 test A1 đạt. Log tại `.scratch/runs/mongo-removal/`.

## Bước 5 — Bỏ hoàn toàn

Không tạo `MongoStateStore`. StateStore chỉ dùng SQLite; không thêm backend lưu trữ MongoDB, dịch vụ MongoDB hoặc dependency thay thế cho nó.

## Runtime trên Space

- SQLite runtime nằm trên đĩa local của Space, tách khỏi DB release chỉ đọc.
- Chấp nhận restart Space về baseline; không yêu cầu giữ runtime qua restart Space.
- Trong cùng run vẫn giữ giao dịch, bằng chứng, biên nhận và chống cấp trùng.
- Quyết định này không yêu cầu xóa state local hiện tại hoặc sửa DB nguồn.
- Chưa tuyên bố đã triển khai Space hoặc kiểm chứng một lần restart Space thật.

## Thứ tự tiếp theo

Huy đã cung cấp đủ thứ tự mới; không liên quan kế hoạch chín task cũ:

1. `git fetch --all --prune`, merge `origin/main` vào `huy`, giữ cả hai phía khi conflict và báo lại; chạy `pytest -q`, lưu log `.scratch/runs`.
2. Revert MongoDB (đã xong).
3. Task 6: `platform_huy/money.py`, `execute_action` qua `StateStore`/`SqliteStateStore`, tái sử dụng `state.py`; test literal, không mạng; phá guard phải làm test đỏ và có log.
4. Song song giao sub-agent làm deploy Space: Python 3.11/cổng 7860, startup tải private HF dataset qua `snapshot_download`/`HF_TOKEN`, đọc `SEA_RELEASE_DIR`, không đưa truth vào image; nghiên cứu ở `.scratch/research/hf-space-deploy.md`.
5. Bỏ MongoStateStore.
6. Sau task 6 nối EffectGateway thật giữa A1 và executor; viết `.scratch/plans/handover-1300.md` rồi dừng.

Trong lượt này chỉ commit nhánh `huy`; không push hoặc cập nhật main. Không hỏi Huy khi đang đi ăn; chọn phương án an toàn và ghi rõ quyết định.

## Nhật ký và quyết định triển khai

- 12:27 VN: fetch cả hai remote và prune; `origin/main` là fork, `upstream/main` là repo team nên merge cả hai vào `huy`. Không conflict. Baseline 518 test đạt; log `.scratch/runs/lunch/baseline/pytest.log`.
- Hai worker độc lập dùng worktree `lunch-money` và `lunch-deploy`; controller giữ phần tích hợp và review. Không sửa contracts hoặc source DB.
- StateStore chỉ dùng SQLite có sẵn. Bằng chứng cấp tiền phải được producer server đã cấu hình ghi vào runtime; thiếu bằng chứng hoặc producer thì từ chối, không suy ra “không bất khả kháng” từ dữ liệu trống.
- Gate tiền kiểm A3 hiện tại theo quyết định 90 phút. Đây là lựa chọn bảo thủ cho demo; không nới gate để làm ca thành công.
- Dataset HF chưa có repo ID được chốt: cấu hình `SEA_DATASET_REPO`, không tự bịa repo hoặc công khai dữ liệu. Không thực hiện publish/deploy ngoài repo trong lượt này.
- Không chỉnh luật hội thoại của Trúc để che khác biệt key hoặc ngưỡng: adapter phải giữ định danh biên nhận A1, ánh xạ key tiền chuẩn ở platform; các khác biệt ngoài phạm vi adapter ghi trong handover.
- EffectGateway được scope theo principal khách đã xác thực và ServerContext do server cấu hình; mapping bằng chứng A1 sang bằng chứng platform phải được server cung cấp. Không tự tạo bằng chứng không bất khả kháng hoặc giả lịch sử bồi thường.
- Bản tiền lunch coi queue, needs_approval và confirmation_id là một phần nội dung yêu cầu đã khóa sau thành công, bảo thủ hơn plan cũ. Lookup phải khớp cùng nội dung và phạm vi customer/seller; không nhận thành công của yêu cầu khác.
- Tin nhắn xin bồi thường phải nằm trong vòng đời contact: sau mở và không sau đóng nếu có closed_at. Biên nhận đã thành công không phụ thuộc dữ liệu eligibility bị cập nhật sau đó.
- Deploy cho phép Origin HTTPS khớp đúng Host để chạy sau proxy Space; vẫn chặn host khác. Runtime phải ngoài release và không alias core/ops, kể cả hardlink. Chưa build image được vì Docker daemon không chạy; không tự bật dịch vụ hoặc publish ngoài repo.
- Sau triển khai vẫn còn phụ thuộc tích hợp: producer bằng chứng platform, transport chat/HTTP, UI cấp tiền và sửa A1 terminal-rejection/heartbeat 60 phút. Không gọi test SQLite fixture là cấp tiền trên đơn thật hay demo xuyên suốt đã hoàn thành.
