# Ghi chú số liệu cho phần giới thiệu

Đối chiếu ngày 31/10/2026 bằng kết nối SQLite chỉ đọc với `data/release_main/core_14d.sqlite`. Toàn bộ là dữ liệu tổng hợp, tên hư cấu. Thống kê hồi cứu dùng toàn bộ release: đơn tạo 18–31/10 và các sự kiện sau đó đến 08/11; không phải dữ liệu mà agent được thấy tại một tick replay.

Ngày trễ so với `guaranteed_date`, theo ngày Việt Nam trong timestamp nguồn `+07:00`. Không thay ngày cam kết bằng ETA. Các tỷ lệ được làm tròn đến phần trăm nguyên.

## COD trễ/chưa giao bị từ chối: 651/1.474, khoảng 44%

Chỉ xét COD chưa hủy. Nhóm giao trễ/chưa giao gồm đơn có lần giao thành công đầu tiên sau ngày cam kết **hoặc chưa có lần giao thành công**: 1.474 đơn, trong đó 651 từng bị từ chối. Nhóm giao thành công đúng hạn có 7.575 đơn, không đơn nào bị từ chối.

Nhóm 1.474 gồm 731 đơn giao trễ và 743 đơn chưa giao thành công. Không diễn giải đây là tỷ lệ từ chối của riêng các lần giao trễ, hoặc bằng chứng trễ gây ra từ chối: phân nhóm theo kết quả giao cuối cùng có bao gồm đơn bị từ chối rồi không giao thành công.

```sql
WITH d AS (
  SELECT order_id, MIN(attempt_at) AS delivered_at
  FROM delivery_attempts WHERE outcome = 'delivered' GROUP BY order_id
), r AS (
  SELECT DISTINCT order_id FROM delivery_attempts WHERE outcome = 'refused'
)
SELECT CASE WHEN d.delivered_at IS NULL
                 OR substr(d.delivered_at, 1, 10) > o.guaranteed_date
            THEN 'late_or_undelivered' ELSE 'on_time_delivered' END AS cohort,
       COUNT(*) AS orders,
       SUM(r.order_id IS NOT NULL) AS refused,
       SUM(d.delivered_at IS NULL) AS undelivered
FROM orders o LEFT JOIN d USING (order_id) LEFT JOIN r USING (order_id)
WHERE o.payment_method = 'COD' AND o.cancelled_at IS NULL
GROUP BY cohort;
```

Kết quả: `late_or_undelivered = (1474, 651, 743)`; `on_time_delivered = (7575, 0, 0)`.

## Shop tự giao: 444/619 đơn giao trễ đã bàn giao đúng hạn, khoảng 72%

Chỉ xét `channel = 'seller_self'` và đã giao thành công sau ngày cam kết. Bàn giao đúng hạn nghĩa là scan `handed_over` đầu tiên nằm trong `seller_prepare_days = 2` ngày kể từ khi tạo đơn. Không áp dụng tỷ lệ này cho tất cả đơn trễ của mọi kênh.

```sql
WITH d AS (
  SELECT order_id, MIN(attempt_at) AS delivered_at
  FROM delivery_attempts WHERE outcome = 'delivered' GROUP BY order_id
), h AS (
  SELECT order_id, MIN(event_at) AS handed_over_at
  FROM scan_events WHERE status = 'handed_over' GROUP BY order_id
)
SELECT COUNT(*) AS delivered_late,
       SUM(julianday(h.handed_over_at) - julianday(o.created_at) <=
           CAST((SELECT value FROM policy WHERE key = 'seller_prepare_days') AS REAL))
         AS handed_over_on_time
FROM orders o JOIN d USING (order_id) LEFT JOIN h USING (order_id)
WHERE o.channel = 'seller_self'
  AND substr(d.delivered_at, 1, 10) > o.guaranteed_date;
```

Kết quả: `619`, `444`.

## 158 đơn giao hỏng lần 3: không đơn nào giao thành công

Cả 158 đơn đều từng vào một trong ba trạng thái `returning`, `returned`, `waiting_to_return`. Có 49 đơn đã hoàn về kho; 109 đơn chưa hoàn tất, gồm 92 đang hoàn, 12 chờ hoàn và 5 hoàn thất bại. Vì vậy không ghi “158 đơn đều đã hoàn về kho” hoặc gọi cả 109 đơn là đang vận chuyển hoàn.

```sql
WITH t AS (
  SELECT DISTINCT order_id FROM delivery_attempts
  WHERE attempt_no = 3 AND outcome <> 'delivered'
)
SELECT COUNT(*) AS third_failure_orders,
       SUM(EXISTS(SELECT 1 FROM scan_events s WHERE s.order_id = t.order_id
           AND s.status IN ('returning', 'returned', 'waiting_to_return'))) AS return_workflow,
       SUM(EXISTS(SELECT 1 FROM scan_events s WHERE s.order_id = t.order_id
           AND s.status = 'returned')) AS returned,
       SUM(EXISTS(SELECT 1 FROM scan_events s WHERE s.order_id = t.order_id
           AND s.status = 'delivered')) AS delivered_scan,
       SUM(EXISTS(SELECT 1 FROM delivery_attempts a WHERE a.order_id = t.order_id
           AND a.outcome = 'delivered')) AS successful_attempt
FROM t;
```

Kết quả: `158, 158, 49, 0, 0`. Phân bố trạng thái cuối:

```sql
WITH t AS (
  SELECT DISTINCT order_id FROM delivery_attempts
  WHERE attempt_no = 3 AND outcome <> 'delivered'
), s AS (
  SELECT s.*, ROW_NUMBER() OVER (
    PARTITION BY s.order_id ORDER BY event_at DESC, ingested_at DESC, event_id DESC
  ) AS rn
  FROM scan_events s JOIN t USING (order_id)
)
SELECT status, COUNT(*) FROM s WHERE rn = 1 GROUP BY status;
```

Kết quả: `returned=49`, `returning=92`, `waiting_to_return=12`, `return_failed=5`.
