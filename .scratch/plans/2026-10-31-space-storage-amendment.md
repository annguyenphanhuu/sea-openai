# Điều chỉnh lưu trữ cho demo trên Space

Quyết định của Huy ngày 31/10/2026. Huy đã xác nhận bước 2/bước 5 là trong tin nhắn, không có file kế hoạch gốc cần tìm. Bản ghi chính thức nằm tại [decisions-lunch.md](decisions-lunch.md). Không đổi số thứ tự hoặc nội dung Task 2/Task 5 của kế hoạch platform chín task.

## Bước 2 — Gỡ PR MongoDB khỏi main

1. Fetch repo team và merge cập nhật main vào nhánh Huy.
2. Chạy `git revert -m 1 76abd17` để gỡ PR #8. Giữ các log audit cũ ở local, ngoài Git; không đưa lại log bị PR này loại khỏi tracking.
3. Cài requirements trong môi trường sạch không có `pymongo`; kiểm `import contracts`, chạy `pytest -q` và riêng `pytest -q care_truc/tests`.
4. Khi kiểm tra đạt, tích hợp nhánh Huy vào main và push sau khi fetch/merge lại cập nhật của team. Không rewrite lịch sử remote.

## Bước 5 — Loại bỏ

Không làm MongoStateStore; StateStore chỉ có bản SQLite. Không thêm dependency, secret hoặc dịch vụ MongoDB.

## Phạm vi runtime đã chốt

Runtime nằm trên đĩa local của Space. Chấp nhận restart Space về baseline; persistence qua restart Space không phải yêu cầu demo. Không tự xóa state đang chạy hoặc thay đổi DB nguồn khi thực hiện điều chỉnh kế hoạch này. Trong cùng run, giao dịch, bằng chứng, biên nhận và chống cấp trùng vẫn bắt buộc.

## Bằng chứng kiểm tra

Revert được thực hiện trên Huy, giữ phần loại log khỏi Git. Môi trường mới được cài từ requirements sau revert và xác nhận không có module `pymongo`: 518 acceptance test đạt, 96 test A1 đạt. Output lưu ở `.scratch/runs/mongo-removal/` (local, gitignored). Việc này kiểm chứng loại dependency MongoDB, chưa chứng minh đã triển khai hoặc reset một Space thật.
