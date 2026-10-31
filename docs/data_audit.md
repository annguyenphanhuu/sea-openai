# Kiểm tra dữ liệu ngày 31/10/2026

## Phạm vi và cách kiểm

Nguồn đã được tìm thấy tại `E:\Master_CS\projects\sea-openai-hackathon\data`. Đã copy `release_main/`, `tiny/` và `metadata.yml` vào `E:\Sea_openai\sea-openai\data/`. Không copy bộ heldout, backup hoặc `truth_main.sqlite`; chúng không cần cho runtime và không được dùng để lộ đáp án tương lai cho agent.

Đọc cả bốn DB bằng SQLite URI `mode=ro` và `PRAGMA query_only=ON`. `PRAGMA quick_check` trả `ok` cho cả bốn. Hash bản copy khớp file nguồn; hash hai DB release cũng khớp manifest. Không cập nhật sim_clock, index hoặc nội dung DB. `data/` được gitignore; báo cáo này chỉ ghi số liệu tổng hợp.

Tài liệu release khai báo đây là dữ liệu tổng hợp có sẵn. Những đoạn văn trong DATA/QUICKSTART không thay thế quy tắc Huy đã chốt: đặc biệt không làm theo hướng dẫn cập nhật sim_clock nguồn, và không dùng chính sách voucher cũ làm điều kiện xu mới.

## Quy mô đo trực tiếp

| Bảng | Release main | Tiny |
| --- | ---: | ---: |
| orders | 14.687 | 3.000 |
| shipments | 13.543 | 2.759 |
| scan_events | 125.827 | 25.758 |
| delivery_attempts | 15.011 | 3.103 |
| linehaul_trips | 2.388 | 2.174 |
| linehaul_reports | 571 | 0 |
| compensation_ledger | 2.701 | 400 |
| tickets | 535 | 300 |
| metrics | 291.456 | 0 |
| logs | 11.607 | 0 |
| alerts | 44 | 0 |
| deploy_events | 73 | 0 |
| webhook_inbox | 36.874 | 0 |

Release có đơn ở đủ 14 ngày 18–31/10/2026. Ngày cam kết từ 20/10 đến 07/11. Scan nguồn từ `2026-10-18T00:03:41+07:00` đến `2026-11-08T19:32:24+07:00`; ingestion từ `2026-10-18T00:05:53+07:00` đến `2026-11-08T19:34:22+07:00`. Metrics từ 18/10 00:00 đến 08/11 23:55, trên 8 services và 11 loại metric. Đây là 14 ngày tạo đơn có phần đuôi kết quả, không phải mọi bảng đều dừng ở 31/10.

## Chất lượng và trường hợp nghiệp vụ

- Release: 0 ngày cam kết thiếu/sai định dạng; 0 giá trị đơn null/0/âm. Cả 14.687 giá trị là integer, min **6.500**, max **20.154.000** VND.
- Các cột đã parse toàn bộ: orders.created_at, scan_events.event_at/ingested_at, metrics.ts, webhook_inbox.received_at: 0 timestamp sai, 0 timezone thiếu, cùng offset +07:00. Không khẳng định mọi cột khác đã qua cùng kiểm tra.
- Scan: 0 event_at/ingested_at null, 0 ingestion trước event. Có **4.482 scan lag ingestion >30 phút**, tối đa 420,2 phút. Đây là độ trễ nhận bản ghi, không tự chứng minh mọi feed đó phải mang nhãn stale theo D3.
- Có **8.434 nhóm cùng ingested_at**, tối đa 12 dòng/nhóm. Không checkpoint giữa nhóm rồi dùng `>` để bỏ mất các dòng còn lại.
- Có 83 carrier_event_id trùng, dư 83 dòng. Retry/dedup cần bằng chứng; không xóa record nguồn. Carrier_event_id null có thể hợp lệ theo loại hãng/scan.
- Đã kiểm các liên kết orders→customer/seller, shipments→order, scans→order/shipment, attempts/returns→order, reports→trip, tickets→customer: **0 dòng mồ côi** ở các quan hệ này.
- Riêng ledger: **1.115/2.701 dòng không tìm được order_id trong orders của lát release**. Không được mặc định join lịch sử luôn đầy đủ hoặc âm thầm suy khách từ các dòng đó. 0 nhóm idempotency key lịch sử bị trùng trong các key khác null đã kiểm.
- Exception có sẵn: lost **16**, damaged **12**, return_failed **23** đơn. waiting_to_return có 54 đơn nhưng không thuộc exception theo D2.
- Trong 12.759 đơn đã có scan delivered: **1.126 giao sau ngày cam kết**, trong đó **277 giao trễ ≥2 ngày**. Đây là thống kê hồi cứu trên toàn DB, không phải danh sách đã đủ điều kiện cấp xu tại một tick: còn phải loại lỗi khách/bất khả kháng và có yêu cầu text đúng phiên.
- Có reason codes và call_attempts cho giao thất bại; 2 lần customer_unreachable có call_attempts=0. Không quy lỗi khách chỉ dựa vào chữ của tài xế.
- External events có 2 flood_alert, 1 weather_alert, 1 sale_campaign, 21 ops_chat. Có dữ liệu đối chiếu tác động ngoài hệ thống, nhưng không có một cột force_majeure đáng tin sẵn cho từng đơn; cần nối thời gian/địa bàn/bằng chứng.
- Ledger lịch sử gồm voucher 1.818, refund 882, shipping_fee_refund 1; chưa có coins. Không lấy số lượng lịch sử làm output của hệ thống mới.
- Tickets: app_chat 342, zalo 93, email 69, hotline_note 31. Tickets có customer_id nhưng không có order_id riêng; mã trong text phải đối chiếu chủ đơn. Không có cờ chứng minh chat đó do A1 mở.

## Giới hạn cần đưa vào implementation

1. **Tiny không đủ cho D1/A3:** cả 3.000 guaranteed_date đều null; toàn bộ 7 bảng ops rỗng, không có linehaul_reports hay sim_clock/view as-of. Dùng tiny cho plumbing/nhánh thiếu dữ liệu; dùng release để kiểm ngày cam kết, telemetry và demo đầy đủ. Không điền ngày cam kết giả để làm test xanh.
2. **Cursor không đồng nhất giữa bảng:** chỉ core.scan_events có cột ingested_at; ops không có cột này. Giữ cursor scan ingested_at. Adapter đọc metrics/logs theo ts, webhook theo received_at và che processed_at tương lai; các bảng khác theo cột nguồn tương ứng. Không ALTER DB để ép schema đồng nhất.
3. **Bẫy sim_clock:** cả hai release đang giữ `2026-10-28T12:00:00+07:00`; view v_*_asof phụ thuộc giá trị này. D5 cấm sửa DB, nên không thể điều khiển replay bằng UPDATE sim_clock. Phải dùng truy vấn tham số và che trường tương lai tương đương ở adapter riêng.
4. **Ledger ngoài lát:** đủ bằng chứng để demo xử lý đơn trong lát, chưa đủ để khẳng định mọi phép đối soát lịch sử theo khách hoàn chỉnh. Không áp một hạn mức lịch sử mới không được Huy yêu cầu; báo rõ dữ liệu thiếu khi cần đối soát.
5. **Runtime chưa có:** heartbeat A3, feed health, phiên A1 mở, text xin xu, xác nhận hủy, phê duyệt và ledger mới do app tạo trong state. Không cần sinh world data để lấp những bảng này; chưa có chúng không phải lỗi release.
6. **Ground truth:** audit không mở truth_main.sqlite. Không thể báo accuracy A2 hoặc độ chính xác ETA khi chưa có mô hình và quy trình đánh giá tách biệt. Không cho agent nhìn kết cục sau tick để dự đoán chính tick đó.

## Kết luận sử dụng

**Release đủ để bắt đầu xây và demo pipeline A3→A2→A1 dựa trên bằng chứng**, có ca trễ, exception, khách không nhận, ingestion lag và telemetry. Điều kiện là adapter phải chống future leakage, phân biệt timestamp nguồn/ingestion, xử lý ledger ngoài lát và thu thập trạng thái chat/confirmation trong runtime.

**Chưa thể khẳng định mọi ca nghiệp vụ đã được phủ đầy đủ** khi chưa chạy acceptance/integration. Tiny không thay thế release cho D1 hoặc A3. Các giới hạn trên cần được test chéo theo team_plan, không được che bằng dữ liệu tự sinh.

## Hash DB đã kiểm

| File | SHA-256 |
| --- | --- |
| release_main/core_14d.sqlite | `65c820444b12bd644416f8d7688b1581ed9ef09f2bac5a1583168f63ec10f153` |
| release_main/ops_14d.sqlite | `d4a5a4f6c4140d75a39d7410331b696df8f6947f7f36a25fbf02fbb87b50afeb` |
| tiny/core.sqlite | `dc862259e1922cfe7e3c4006c806a2cfdd6f3126409080225b5289bc4e25af58` |
| tiny/ops.sqlite | `4fd8c0fd9f5dab4885805947d9825b8fa6f8cedef715d8e705f5dac537322f60` |
