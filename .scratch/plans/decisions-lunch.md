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

Tiếp tục theo thứ tự Huy đã giao trong tin nhắn; bỏ bước 5. Ngữ cảnh hiện có chỉ xác định rõ bước 2 và bước 5; cần nhận lại nội dung các bước còn lại trước khi triển khai, không tự suy ra từ kế hoạch chín task cũ.
