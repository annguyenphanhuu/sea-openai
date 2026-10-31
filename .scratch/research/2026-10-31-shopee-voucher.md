# Shopee Việt Nam: voucher giao trễ và lựa chọn cho hackathon

Ngày truy cập: **31/10/2026**. Đây là nghiên cứu và đề xuất, chưa sửa policy/spec/code, chưa có provider phát voucher. Phạm vi chỉ Shopee Việt Nam; không lấy quy định quốc gia khác làm căn cứ.

## 1. Nguồn chính thức đã mở được

**S1:** [Shopee Help — GIAO NHANH ĐÚNG HẸN, FAQ 147164](https://help.shopee.vn/portal/4/article/147164). Đã đọc toàn văn bằng web open; không bị robots/access block. Trang không hiển thị ngày xuất bản/cập nhật; nêu chương trình bắt đầu 03/04/2024, đến thông báo mới. Không khẳng định lần sửa gần nhất của trang.

Bản tóm tắt tiếng Anh dưới đây giữ ngắn để giới hạn phần nội dung diễn giải từ một nguồn:

> One voucher per qualifying late order, for a subsequent purchase. Trigger: guaranteed date passed without prior delivery contact; timely failed contact attributable to the buyer excludes eligibility. Claim within seven days of the guaranteed date; use within seven days after saving. Value varies at Shopee's discretion: no fixed VND10,000 stated. Exclusions include domestic seller self-shipping, seller/Shopee cancellation, and return/refund requested before successful delivery. Redemption excludes top-ups/services, ShopeeFood and express shipping; app only. The guaranteed date differs from a changing delivery estimate. No explicit force-majeure, minimum-spend or coin-stacking rule appears here. See sections 4–9 for exact terms, including product exclusions.

Nguồn của toàn bộ đoạn tóm tắt: [S1, mục 4–9](https://help.shopee.vn/portal/4/article/147164). Đây là các điều kiện đang hiển thị khi truy cập, không phải xác nhận Shopee sẽ giữ nguyên sau ngày này. Chưa truy cập được một voucher cụ thể trong tài khoản để kiểm tra điều kiện riêng.

**S2:** [Shopee Blog — Shopee Choice là gì?](https://shopee.vn/blog/shopee-choice-la-gi/), ngày bài viết **20/08/2025**, đã mở và đọc thân bài. Bài quảng bá voucher giao trễ **15.000đ** cho Choice; một ưu đãi **10K cho đơn từ 30K** ở đoạn khác là khuyến mãi mua sắm thông thường. Không dùng bài quảng bá này để xác nhận giá trị bồi thường chung hiện tại. Không tìm thấy bằng chứng chính thức đã mở xác nhận “Shopee hiện luôn cho 10K vì giao trễ”.

## 2. Giới hạn và manh mối chưa xác minh

- Kết quả tìm kiếm có bài bên thứ ba nói 10K, có bài vừa nói 15K vừa nói 10K. Không sử dụng chúng làm bằng chứng policy, không suy chúng là phiên bản lịch sử chính xác.
- Không gặp chặn truy cập ở hai nguồn chính thức trên. Giới hạn là thiếu điều kiện của voucher được phát cho tài khoản/đơn cụ thể và thiếu ngày cập nhật FAQ.
- Việc FAQ không nêu rõ một điều kiện không chứng minh Shopee cho phép điều đó. Đặc biệt, không suy ra “bất khả kháng vẫn tự động được voucher”, “không có đơn tối thiểu”, hoặc “cộng dồn với xu”.

## 3. Đối chiếu quyết định dự án

Các căn cứ nội bộ đã đọc: [AGENTS.md](../../AGENTS.md), [thiết kế platform](../specs/2026-10-31-huy-platform-design.md), [nghiên cứu executor, mục 8](2026-10-31-huy-execution.md), `contracts/types.py`.

- Scope đã duyệt trước steering mới là coins + cancel. Thiết kế hiện nhận diện voucher nhưng trả `policy_not_configured`.
- Matrix hiện chỉ cho `voucher` từ `source='rule'`. LLM/A2/A3 không tự chọn số tiền hay trực tiếp phát voucher; source phải do server xác thực, không tin JSON caller.
- Steering mới của Huy đề xuất **10.000 VND** cho voucher. Đây là giá trị policy dự án muốn chọn, không cần và không nên trình bày thành policy Shopee đã xác nhận.
- Luật coins hiện cần trễ ít nhất hai ngày lịch VN, khách yêu cầu bằng text trong chat A1 mở, xác định không lỗi khách và không bất khả kháng, kiểm lịch sử và once/order. Chưa có quyết định rằng voucher chia sẻ toàn bộ luật đó hay là quyền lợi khác.
- Evidence fault/FM chưa đủ phải giữ unknown/review; thêm loại voucher không tự biến unknown thành eligible. Không thay coins bằng voucher nếu chưa có quyết định riêng.

## 4. Ba phương án đề xuất, chưa được duyệt

| Phương án | Policy dự án đề xuất | Lợi ích và chi phí |
| --- | --- | --- |
| A — Một quyền lợi bồi thường | Voucher cố định 10.000 VND, cùng điều kiện đủ như coins; khách chọn một trong hai, một lần bồi thường/order dùng chung lịch sử. | Ít rule mới, tránh trả hai quyền lợi. Cần Huy duyệt quyền lựa chọn và mapping lịch sử; không tự bỏ quyền coins đã có. |
| B — Voucher sớm, coins muộn | Voucher 10.000 VND khi qua guaranteed_date, có bằng chứng đủ điều kiện; coins vẫn từ hai ngày theo luật hiện có. | Trải nghiệm gần ý tưởng đảm bảo giao đúng hẹn. Phải chốt voucher có cộng coins không; thêm lifecycle và chi phí. Mọi bypass điều kiện FM cần policy rõ riêng. |
| C — Chốt mệnh giá, hoãn phát | Ghi nhận ý định 10.000 VND; executor tiếp tục `policy_not_configured` đến khi đủ rule và lifecycle. | Có thể tiếp tục phần coins/cancel đang duyệt; chưa demo được cấp voucher. Không hứa voucher đã vào ví. |

Khuyến nghị để cân nhắc: **A** nếu mục tiêu là thêm một cách bồi thường nhỏ trong hackathon mà giữ ít rule. Đây không phải quyết định thay Huy. B có ý nghĩa nếu Huy thực sự muốn quyền lợi giao trễ sớm và chấp nhận chi phí cộng dồn. Không triển khai nhánh nào chỉ dựa trên nghiên cứu này.

## 5. Các quyết định cần chốt trước khi mở grant

1. **Eligibility/trigger:** voucher dùng cùng điều kiện coins hay ngay sau hết ngày đảm bảo? Cần text request hay hệ thống cấp theo rule? Đơn canceled, returned/refund, customer fault và FM xử lý cụ thể ra sao? Unknown evidence vẫn review trừ khi có policy được duyệt rõ.
2. **Quan hệ với coins:** voucher thay thế có quyền chọn, bổ sung, hay loại trừ? Một lần mỗi đơn áp dụng chung compensation hay riêng từng kind? Historical voucher/refund nào tiêu thụ quyền lợi nào?
3. **Điều kiện sử dụng:** deadline nhận, ngày hết hạn sau nhận, timezone và phép so sánh boundary, min-spend, phạm vi shop/sản phẩm, số lần dùng, cộng dồn các ưu đãi khác. Có thể đề xuất 7 ngày lấy cảm hứng S1, nhưng không tự thêm vào luật dự án.
4. **Hiệu lực thực tế:** chỉ runtime entitlement/ledger cho demo hay provider ngoài? Chưa có provider thì receipt phải nói rõ trạng thái local; không hứa mã dùng được tại Shopee. Nếu redeem ngoài scope, phải mô tả rõ và không dựng endpoint giả là hệ thống đã tích hợp.
5. **Idempotency và audit:** một grant/order theo policy đã chọn, unique constraint khi concurrent/retry; evidence và policy version; lịch sử không rõ mapping thì review. Server tính lại giá trị cố định 10.000 VND, không lấy amount từ LLM.

Có thể gom câu hỏi đầu tiên cho Huy: “Voucher 10K là một lựa chọn cùng điều kiện với xu, hay quyền lợi thêm ngay khi giao trễ; có được nhận cả hai không?” Sau câu trả lời mới chốt expiry/min-spend/lifecycle trong đặc tả. Các mục chưa được Huy quyết định vẫn là đề xuất, không trở thành default âm thầm.
