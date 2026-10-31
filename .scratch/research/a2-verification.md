# Kiểm tra sâu A2 — 31/10/2026

## Kết luận

Logic A2 và các ranh giới đã kiểm tra hoạt động đúng sau sửa lỗi: **469 test pass,
0 fail/error/skip**, gồm **198 case mới** trong đợt này. Chưa có cơ sở gọi mô hình
ETA/xác suất trễ đủ tốt để tự động quyết định liên hệ. Chưa kiểm chứng luồng thật
A3 → A2 → A1, HTTP/auth, voice hoặc thực thi tiền.

Nhánh: `nguyen/a2-verification`. Đã tích hợp `origin/main` tới `76abd17`, gồm nền
DTO/state/migration của Huy và cấu hình MongoDB. Chỉ sửa implementation A2 và thêm
test trong `acceptance_huy/`; không sửa test của Trúc, contracts hoặc dependencies.
Python kiểm thử: 3.11.10 trong `.venv`. Các dependency mới từ main được cài đúng
`requirements.txt`; không kết nối MongoDB thật trong đợt kiểm tra.

## Lỗi tìm được và cách xử lý

| Vấn đề | Tái hiện và sửa |
| --- | --- |
| Lịch sử hoàn/hủy trước delivery vẫn được tính là mẫu giao thành công | Fixture có terminal sau 10 giờ, delivery sau 20 giờ: code cũ lấy 20 giờ/delivered. Nay censor ở 10 giờ; tie cũng không tính thành công, chặng sau terminal không trở lại tập huấn luyện. Delivery xảy ra trước return vẫn là delivery. |
| Thứ tự các lần giao làm đổi lỗi khách | Đảo hai dòng attempt cũ/thành công mới làm đổi kết luận. Adapter nay sắp attempts theo timestamp và ID trước chọn bản ghi cuối. |
| Snapshot tự cấp có thể đưa dữ liệu tương lai vào forecast | Reader chuẩn đã lọc, nhưng adapter chưa tự kiểm cutoff trước fit. Nay từ chối timestamp tương lai/không timezone ở created/cancelled, scan event/ingestion, attempt và report. Không biến snapshot sai thành forecast mang timestamp hiện tại. |
| Cùng câu hỏi quản lý sinh lại mỗi tick khi feed vẫn lỗi | Timestamp progress thay đổi dù giá trị và bằng chứng giữ nguyên. Khóa mới bỏ riêng clock của progress và chuẩn hóa thứ tự bằng chứng; vẫn giữ giá trị/provenance trong khóa và timestamp đầy đủ trong audit. |

Nhóm regression đầu tiên tái hiện **22 fail / 1 pass** trước bản sửa adapter.
Ca câu hỏi qua tick cũng fail trước bản sửa service; ca scan ingest đúng tick bắt
được thêm ảnh hưởng gián tiếp của timestamp lên thứ tự bằng chứng. Các ca đó đều
pass sau sửa. Không đổi expected của test cũ để làm xanh.

Khóa câu hỏi có progress thay đổi so với bản cũ. Dùng run demo mới khi chuyển
phiên bản; bản sửa không tự gộp/migrate các câu hỏi đã lưu bằng khóa cũ.

## Phạm vi kiểm thử

- 128 tổ hợp các điều kiện ưu tiên trạng thái; các test cũ giữ kiểm tra ngày VN,
  giao đúng nửa đêm, late_days, fault, ETA và probability.
- Từng feed với missing/stale/corrupt, thiếu snapshot, timestamp nguồn quá hạn,
  timestamp nguồn/check/ingestion tương lai; đúng 30 phút và hơn 1 microsecond.
- Snapshot → adapter → progress → assessment → payload qua nhiều tick; retry,
  khôi phục JSON, đứng yên hai khoảng 30 phút, đổi vị trí, mất trust và bỏ tick.
- Ngày đặt/bàn giao/cam kết không lẫn; cùng cutoff; tương đương múi giờ;
  chống dữ liệu tương lai ở nguồn và chống sửa input ngoài ý muốn.
- Lịch sử forecast terminal/censor, ngưỡng hỗ trợ delivery thực, thứ tự attempts,
  dedup scan ở 119/120/121 giây, driver text không thay logistics hoặc quyền.
- QuestionStore rollback/idempotency, câu hỏi không nhân khi chỉ đổi clock;
  bằng chứng/giá trị tiến độ thay đổi vẫn được phân biệt.
- Ghép A2 với `bootstrap`, `canonical`, `immediate` và migration thật của Huy:
  questions/progress/payload/checkpoint commit hoặc rollback cùng nhau. Đây là
  kiểm thử composition bằng caller SQL với state primitives, **không phải** test
  tick runner/A3 đã hoàn thiện.
- Bảy negative controls trên bản sao tạm: sai terminal label, bỏ sắp attempts,
  bỏ kiểm cutoff, đổi biên freshness, tăng progress khi retry, bỏ ingestion filter,
  đưa clock trở lại question key. Tất cả bị test phát hiện; checkout không bị mutate.

## Replay release chỉ đọc

Đã chạy 9 tick: 21/10 12:00, 24/10 16:00, 25/10 12:00, 26/10 12:00,
27/10 12:00, 28/10 12:00/12:30/13:00 và 31/10 12:00, giờ Việt Nam.
Tổng **78.104 lượt đánh giá**, có lặp đơn giữa tick, không phải số đơn duy nhất.
Tick cuối có 13.988 đơn visible, 12.979 đơn không hủy được đánh giá.

Không tạo A3 health: mọi assessment trả unknown_feed, confidence 0, ETA null;
metadata ngày đặt/bàn giao bị ẩn theo trust. Mỗi tick kiểm số lượng/ID, cutoff
evidence, JSON hợp lệ, repeat tick và restore progress cho cùng kết quả. Thời gian
1,80–13,42 giây/tick bao gồm đọc, tính, serialize và lặp kiểm tra; đây không phải
benchmark SLA hoặc bài kiểm tra tải đồng thời.

CLI thực tế tại 28/10 12:00: 10.193 assessment; retry giữ nguyên hash mọi file
output; rewind bị từ chối và không đổi output; thiếu A3 state không tạo DB giả.
Sau bản sửa question key, chạy riêng 28/10 12:00 → 12:30: **13.858 câu hỏi có
bằng chứng nguồn không đổi giữ nguyên ID**. Các bằng chứng thực sự thay đổi không
bị yêu cầu giữ ID cũ.

Hash nguồn trước/sau không đổi:

| File | SHA-256 |
| --- | --- |
| core_14d.sqlite | `65c820444b12bd644416f8d7688b1581ed9ef09f2bac5a1583168f63ec10f153` |
| ops_14d.sqlite | `d4a5a4f6c4140d75a39d7410331b696df8f6947f7f36a25fbf02fbb87b50afeb` |

## Chất lượng dự báo

Đã chạy lại validation độc lập trên tick 25/26/27 tháng 10 lúc 12:00, cùng cửa sổ
72 giờ, observed-through 30/10 12:00. Không cấp trust/contact authority từ kết quả.

- 10.604 lượt active; 8.497 forecast, độ phủ **80,13%**.
- 4.987 ETA có delivery để chấm: **MAE 16,55 giờ**, bias +1,50 giờ.
- 2.519 nhãn risk đã biết và 179 chưa biết: **Brier 0,1142**, baseline luôn dự báo
  không trễ **0,0790**; trên nhãn đã biết, baseline tốt hơn.
- 3.015 forecast chưa có delivery quan sát và 493 terminal-before-delivery.
  Censoring/selection bias còn tồn tại; các mẫu lặp theo đơn không độc lập.

Các số tổng hợp này không cải thiện so với lần đo đã ghi trước đó trên cùng cửa
sổ. Bản sửa xử lý lỗi biên; không phải một lần hiệu chỉnh hoặc nâng chất lượng model.

## Bằng chứng và tái lập

Lệnh regression cuối: `.venv/Scripts/python.exe -m pytest -q
--junitxml=runs/a2-verification/full.xml`: **469 passed in 9.14s**, exit 0.
Import contracts/A2 và `git diff --check` đều pass.

Artifacts local, được gitignore, ở `runs/a2-verification/`:
`full.log`, `full.xml`, `history-before.log/xml`, `questions-before.log`,
`release-evidence.json`, `release-question-keys.json`, `forecast-quality.json`,
`negative-controls.json` và log từng negative control. Script tái lập là
`check_release.py`, `check_release_questions.py`, `negative_controls.py`.

Giới hạn còn lại: chưa đo mô hình trên heldout; không đọc truth/heldout; chưa test
A3 tạo health thật, tick runner crash/concurrency, A1/HTTP/auth/voice hoặc cấp tiền.
Nền state của Huy đã có, nhưng các test composition không chứng minh toàn pipeline
hoàn tất. Bước tiếp theo là nối A2 vào tick runner thật và kiểm thử failure/recovery
ở ranh giới đó; cải thiện model cần một đợt đánh giá riêng.
