# SEA OpenAI — Chăm sóc đơn giao trễ có kiểm soát

**Ascendant · An Nguyên, Huy, Trúc · 31/10/2026**<br>
**Hướng thi:** Autonomous & Adaptive AI<br>
[Demo trực tuyến](https://sea-openai-ops-559aa5.azurewebsites.net/) · [Repo bài thi](https://github.com/annguyenphanhuu/sea-openai)

## Vấn đề

Đơn giao chậm khiến khách thiếu thông tin và người bán khó biết trách nhiệm nằm ở đâu. Một thông báo sai vì scan chưa về có thể làm tình huống tệ hơn; một lời hứa hoặc khoản đền bù thiếu bằng chứng tạo thêm rủi ro. Nhóm muốn hệ thống biết khi nào nên giải thích, hỏi lại, chuyển người và dừng hành động.

Ba quan sát sau mô tả **dữ liệu tổng hợp “Chợ Phố”**, không phải thống kê Shopee. Chúng truy vấn toàn bộ đơn tạo 18–31/10/2026 cùng các scan/lần giao trong release đến 08/11; là phân tích hồi cứu, không phải thông tin agent được nhìn trước tại tick demo. Một số bảng khác còn có bản ghi đến 10/11. Tỷ lệ làm tròn đến phần trăm nguyên. Nguồn và SQL: [docs/pitch-notes.md](https://github.com/annguyenphanhuu/sea-openai/blob/main/docs/pitch-notes.md).

| Quan sát | Phạm vi và cách đọc |
| --- | --- |
| **651/1.474 ≈ 44%** | COD chưa hủy, đã giao sau ngày cam kết **hoặc chưa giao thành công**, từng có lần bị từ chối. Nhóm gồm 731 giao trễ và 743 chưa giao; không suy ra trễ gây từ chối. |
| **444/619 ≈ 72%** | Chỉ đơn kênh `seller_self` đã giao trễ: lần bàn giao đầu trong hạn chuẩn bị 2 ngày. Không áp dụng cho mọi kênh hoặc mọi đơn trễ. |
| **158 đơn giao hỏng lần 3** | Không đơn nào giao thành công trong release; tất cả từng vào quy trình hoàn. Chỉ 49 đã về kho; 109 chưa hoàn tất, gồm 92 đang hoàn, 12 chờ hoàn và 5 hoàn thất bại. |

Các con số nêu nhu cầu hỗ trợ và giải thích trách nhiệm; chúng **không đo mức cải thiện do hệ thống**.

## Giải pháp và quyền hành động

```text
NEXT (+30 phút) → snapshot chỉ đọc → A3 kiểm tra độ tin dữ liệu
                                       ↓
                              A2 đánh giá + bằng chứng
                                       ↓
                              A1 chăm sóc qua chat
                                       ↓
               Cửa tiền platform → kiểm điều kiện → biên nhận SQLite
```

**A3** kiểm feed, ghi heartbeat và chặn chủ động khi mất độ tin; Kill chặn ngay, Revive cần lượt chạy mới và feed hợp lệ. **A2** phân loại đơn, đưa ETA và lý do dựa trên bằng chứng; ngày cam kết vẫn là mốc tính trễ theo lịch Việt Nam. Replay chỉ cho thấy dữ liệu đã nhận tại thời điểm mô phỏng. **A1** dùng luật nhận ý định, giải thích từ A2, hỏi xác nhận hủy và chuyển nhân viên.

LLM hiện chỉ chọn **mã câu trong danh mục được duyệt** cho một số lượt giải thích/hỏi rõ; code điền ngày, số tiền và dữ kiện, kiểm tra đầu ra và dùng template khi lỗi. A2/A3 không gọi LLM để quyết tiền. `execute_action` kiểm quyền, nguồn gốc yêu cầu, freshness, điều kiện, số tiền và chống cấp trùng. Xu thành công ghi khóa `xu:{order_id}`; retry không tạo khoản thứ hai. Từ chối vẫn có audit nhưng không khóa vĩnh viễn lần xét lại.

<div class="page-break"></div>

## Bốn cảnh demo

Chạy bản web Python tích hợp, bấm NEXT và chọn đơn release có bằng chứng. Đây là kịch bản kiểm tra hành vi, không phải cam kết mọi ca đều được duyệt.

| Cảnh | Thao tác và kết quả cần quan sát |
| --- | --- |
| **1. Hỏi đơn** | Mở chat do A1 tạo, hỏi “Sao đơn tôi trễ vậy?”. Đối chiếu câu trả lời với ngày cam kết, ETA và bằng chứng A2. Khi bật LLM, xem dấu vết `used_llm`; không mặc định mọi lượt đều gọi model. |
| **2. Xin đền bù** | Với đơn `261021ZS7E76FW`, nhân viên tự xem bằng chứng và ghi xác minh có audit; nguồn không tự chứng minh không có bất khả kháng. Gửi TEXT “Tôi xin xu”. Nếu đủ điều kiện, ledger ghi **26.000 xu** từ giá trị hàng 525.000 VND; gửi lại để kiểm tra không cấp trùng. Đây là quyền lợi nội bộ, không chuyển tiền vào ví thật. |
| **3. Hủy đơn** | Gõ “Tôi muốn hủy đơn”, đọc câu hỏi xác nhận và bấm xác nhận. Quan sát `cancel_request` chờ duyệt trong runtime; không sửa đơn nguồn, không tự hoàn tiền. |
| **4. Tắt A3** | Bấm Kill A3: chặn ngay chủ động liên hệ/cấp xu. NEXT không được tạo liên hệ mới bị cấm. Revive rồi NEXT chỉ phục hồi nếu các gate còn lại cho phép; không tự gỡ `proactive_block`. |

Luật đền bù là chính sách mô phỏng của nhóm: trễ ít nhất hai ngày lịch Việt Nam, khách xin bằng TEXT trong chat A1 mở, không lỗi khách hoặc bất khả kháng, đủ bằng chứng và quyền. Xu bằng 5% giá trị hàng, làm tròn xuống bội 1.000, trong khoảng 10.000–1.000.000. Voucher 10.000 VND có executor riêng và khóa riêng, nhưng chưa được chứng minh qua luồng chat A1 ở mốc đối chiếu.

## Khớp hướng đăng ký, với phạm vi thực tế

Bản đăng ký ngày 15/10 chọn **Autonomous & Adaptive AI**, gồm A1 xử lý khiếu nại, A2 logistics và A3 giám sát/tự khắc phục. Bài thi giữ ba vai trò, tự chạy chuỗi **A3 → A2 → A1** mỗi lần NEXT và thích nghi bằng chặn an toàn, hỏi bằng chứng hoặc chuyển nhân viên. **Phạm vi đã thu hẹp:** chưa chứng minh tự sửa code/rollback hạ tầng, quản lý tồn kho hay hoàn tiền thương mại như ý tưởng ban đầu. Bản demo hiện thể hiện giám sát và điều kiện hành động. [Bản đăng ký gốc trong repo chuẩn bị](https://github.com/vinhhuy12/sea-openai-hackathon/blob/main/day-d/event/du-an-3-agent.md).

## Dùng Codex và bằng chứng

Theo khai báo của nhóm, Codex viết code, test và deploy; Claude chỉ đọc, review, viết prompt trong ngày thi, không sửa code giải pháp. Công việc chia theo quyền sở hữu thư mục; các nhánh triển khai độc lập dùng subagent/worktree riêng, controller tích hợp. Research → spec → review context sạch → plan; có lượt kiểm tra độc lập và log RED/GREEN thực trong `.scratch`. Đây là quy trình hỗ trợ kiểm soát lỗi, không thay thế xác minh của con người.

Mốc đối chiếu code: **`b00d78e`, 14:47:50 +07:00 ngày 31/10**; repo bắt đầu từ `25131a2` lúc 09:09:30, chỉ một dòng README. Log trình duyệt tích hợp ghi nhận NEXT, chat, ledger xu, hủy chờ duyệt, handoff và Kill; log selector ghi một lần gọi model thật. Các lần chạy suite sau merge còn lỗi, nên không công bố tổng test hiện tại đều đạt hoặc accuracy/ROI. [Nhật ký và nguồn kiểm tra](https://github.com/annguyenphanhuu/sea-openai/blob/main/docs/codex-log.md).

## Giới hạn công khai

**Voice đang làm**, chưa tính là hoàn tất. Dữ liệu tổng hợp và xác minh nhân viên trong test không chứng minh tình huống thực. A3 dùng timeout trên 90 phút, trong khi A1 còn kiểm tra heartbeat 60 phút nên có thể chặn sớm hơn. Bản công khai dùng quyền người trình bày, chưa là hệ thống phân quyền khách hàng. SQLite runtime không bảo đảm giữ qua restart; không có ví thật, SMS/PSTN hay số đo hiệu quả kinh doanh. Repo cũ chỉ dùng ý tưởng/kế hoạch, không chép code; dữ liệu chuẩn bị trước và OSS được khai riêng trong [Declarations](https://github.com/annguyenphanhuu/sea-openai/blob/main/docs/declarations.md).
