# Kết quả chạy lại ba kịch bản demo

Ngày kiểm tra: **31/10/2026**, múi giờ Việt Nam (UTC+7).
Mã nguồn đã kiểm tra: **`1a6dd55bd0358ff7c833a6784b7cae8e040709b7`** trên `main`.
Model: **`gpt-5.4-mini`**. **13/13 kiểm tra đạt**: 10 kiểm tra pipeline trên
runtime riêng và 3 lượt hội thoại qua HTTP trên server vừa khởi động lại.
Đây là kiểm tra API/backend cho các thao tác trong hướng dẫn frontend, không phải
bản ghi thao tác bấm toàn bộ giao diện.

## Server sẵn sàng trình diễn

- Địa chỉ: **http://127.0.0.1:8790**. Hai tiến trình demo cũ ở 8790/8791 đã dừng;
  hiện chỉ cổng 8790 phục vụ bản demo mới trong hai cổng này.
- A1 bật LLM; A2 và A3 đều ghi nhận model review `succeeded` sau tick đầu.
- Thời gian replay: **24/10/2026 14:30 +07:00**.
- **6.259 đơn, 30 phiên chat, chưa có bản ghi cấp xu**, liên hệ chủ động được phép.
- Runtime trình diễn: `runs/demo-main-1a6dd55/state.sqlite`.
- Các ca cấp xu, hủy và dừng A3 chạy trong runtime kiểm thử riêng, không làm
  thay đổi ledger hoặc thời gian của runtime trình diễn.

## 1. Hiểu câu hỏi và tư vấn theo bằng chứng — ĐẠT

Đơn: **`261021ZS7E76FW`**. Câu hỏi:

> Could you tell me when my parcel will arrive?

Phản hồi thực tế, `used_llm: true`:

> Bạn dự kiến nhận được hàng vào 24/10/2026 17:00 theo giờ Việt Nam. Mốc này vẫn là dự kiến, chưa phải cam kết giao mới.
>
> Cập nhật vận chuyển gần nhất lúc 24/10/2026 12:58 theo giờ Việt Nam: đang giao hàng.

Khi hỏi **“Mình chờ lâu quá, cần hàng gấp. Khi nào mới nhận được vậy?”**,
phản hồi mở đầu:

> Mình rất tiếc vì bạn phải chờ lâu. Mình hiểu bạn cần biết thời gian nhận hàng để sắp xếp.

Phần sau vẫn giữ ETA **24/10/2026 17:00** và lưu ý chưa phải cam kết giao mới.
Khi khách nói **“Cảm ơn bạn nhé”**, bot trả lời **“Cảm ơn bạn.”**, không hỏi tiếp.
Cách dẫn chuyện có thể thay đổi giữa các lần gọi model; dữ kiện và điều kiện không đổi.

Ca hỏi nguyên nhân không bịa lý do: bot nói chưa có thông tin xác nhận vì sao trễ.
Ca lịch sử đơn **`261018J0R2AF1I`** nêu đúng **3 lần giao chưa thành công,
2 lần không liên lạc được, đang hoàn trả**; không suy diễn bên có lỗi từ các lần giao.

## 2. Chặn cấp tiền thiếu căn cứ và cấp đúng một lần — ĐẠT

| Bước kiểm tra | Kết quả thực tế |
| --- | --- |
| Ép cấp `999999 xu` khi chưa xác minh | Không cấp xu; ledger có 0 dòng; mã `coins_evidence_unavailable` |
| Nhân viên xác minh giả lập trong runtime kiểm thử | Trách nhiệm `carrier`, bất khả kháng `absent`, có bằng chứng và lý do ghi audit |
| Khách gửi `Tôi xin xu` | Đúng một bản ghi **26.000 xu** |
| Khách gửi lại bằng request mới | Ledger vẫn chỉ có **1 bản ghi**, không cấp trùng |
| Ca bổ sung: yêu cầu hủy | Phải xác nhận lần hai; sau xác nhận có **1 yêu cầu `awaiting_review`**, chưa phải hủy thành công |

Xác minh nhân viên là **đầu vào giả lập có ghi audit**, không phải LLM tự kết luận
không có bất khả kháng. Toàn bộ quyền lợi nằm trong SQLite local, không chuyển tiền thật.

## 3. A3 dừng: chặn liên hệ mới, vẫn bàn giao được — ĐẠT

| Bước kiểm tra | Kết quả thực tế |
| --- | --- |
| Tắt A3 | `guard_alive=false`, `proactive_allowed=false` |
| NEXT khi A3 dừng | Tổng liên hệ giữ nguyên **30 → 30** |
| Khách xin gặp nhân viên trong phiên đang mở | Có **1 bàn giao**, không gọi LLM để quyết định |
| Bật A3 nhưng chưa NEXT | Vẫn chưa được liên hệ chủ động |
| NEXT để A3 chạy thật | Đến **15:30**, guard hoạt động và liên hệ chủ động được phép trở lại |

## Bằng chứng kiểm thử

- [Báo cáo 10 kiểm tra pipeline](../runs/demo-recheck-1a6dd55-20261031/report.json).
- [Báo cáo 3 lượt chat qua HTTP](../runs/demo-recheck-1a6dd55-20261031/http_report.json).
- Hash SHA-256 của cả `core_14d.sqlite` và `ops_14d.sqlite` **không đổi** trước/sau kiểm thử.

Hai báo cáo JSON và runtime được giữ local trong `runs/`, không commit lên Git.
Hướng dẫn các bước trình diễn: [DEMO_LLM_VI.md](DEMO_LLM_VI.md).
