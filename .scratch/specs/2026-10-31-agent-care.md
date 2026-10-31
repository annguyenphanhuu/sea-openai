# Thiết kế Agent 1 chăm sóc đơn trễ

Ngày: 2026-10-31. Trạng thái: bản thiết kế chờ duyệt, chưa triển khai.
Phạm vi sở hữu: `care_truc/`. Nhánh: `truc/agent-care`.

## Mục tiêu và quyết định

Khách biết đơn đang gặp vấn đề gì, bằng chứng nào hỗ trợ kết luận, và có thể làm gì tiếp theo. Khách được chuyển nhân viên mà không phải kể lại toàn bộ câu chuyện.

Người dùng đồng ý lấy luồng đề xuất làm trọng tâm: A1 chủ động báo trễ, khách hỏi nguyên nhân, khách yêu cầu hỗ trợ, A1 xử lý đúng điều kiện hoặc chuyển nhân viên. Những lựa chọn kỹ thuật và giới hạn dưới đây là đề xuất của người triển khai, chưa phải quyết định mới của nhóm.

Bản đầu ưu tiên chat tiếng Việt, API cho chat, kiểm soát hành động, và dấu vết giải thích. Web voice là giai đoạn tiếp theo, dùng chung lõi hội thoại. Chưa chọn provider voice, chưa gọi hotline, chưa mô phỏng một cuộc gọi thành công. UI quản lý và HTTP server tích hợp thuộc Huy.

Nguồn yêu cầu: [AGENTS.md](../../AGENTS.md), [team plan](../../docs/team_plan.md), [D1–D5](../../docs/decisions.md), [contracts](../../contracts/types.py), và [nghiên cứu điều phối](../research/2026-10-31-agent-orchestration.md).

## Phạm vi bản đầu

- Nhận `OrderAssessment`, `ContactTask`, guard và context đã được platform xác thực.
- Mở chat chủ động khi guard cho phép. Nhận chat do khách mở, nhưng loại phiên này không đủ điều kiện D4.
- Xử lý 7 intent trong `contracts.types.INTENTS` bằng rules trước khi gọi LLM tùy chọn.
- Giải thích nguyên nhân bằng `reason_codes` và evidence tương ứng, giữ nguyên ngày cam kết và ETA của A2.
- Tạo yêu cầu hủy sau lần xác nhận riêng, gắn đúng khách, phiên, đơn và yêu cầu.
- Xét yêu cầu xu theo D4, tính tiền bằng `late_xu_for`, gửi `Action` qua platform.
- Chuyển nhân viên theo yêu cầu, khi chửi đủ 3 lượt, hoặc khi vượt giới hạn hội thoại.
- Trả bản tóm tắt bàn giao và dấu vết quyết định qua API nội bộ.
- Xử lý retry của message, contact và action, đồng thời lưu phiên để phục hồi sau restart.

Bản đầu không tự đánh giá lại logistics, tự gán lỗi, tự cấp tiền, tự hoàn tiền, tự duyệt hủy, sửa DB nguồn, thay shared contracts, hoặc thêm dependencies. Không chủ động gợi khách đòi xu nhằm lách D4.

## Luồng demo và tiêu chí thành công

Demo tích hợp chọn một đơn thật trong release tại cutoff hợp lệ. A2 và A3 cung cấp dữ liệu đã được phép thấy. Nếu không có đơn thỏa điều kiện xu, demo thể hiện từ chối đúng điều kiện; không sửa dữ liệu để tạo case.

1. Platform đưa contact chủ động cùng assessment đã hoàn tất cho A1.
2. A1 kiểm guard, chuẩn bị lời mở đầu từ mẫu, và platform kiểm guard lần nữa trước gửi.
3. Khách hỏi lý do. A1 giải thích ngắn, cho biết nguồn bằng chứng và thời điểm cập nhật.
4. Khách tự yêu cầu xu bằng text. A1 kiểm D4 và gửi yêu cầu hợp lệ, hoặc giải thích điều kiện chưa đủ.
5. Một nhánh riêng cho khách muốn hủy và xác nhận lại. Nhánh khác cho khách muốn gặp người.
6. Nhân viên nhận bản tóm tắt với nhu cầu, facts, yêu cầu đã gửi và việc đang chờ.
7. Người vận hành xem một case LLM trả số tiền hoặc ngày lạ bị từ chối. Một case guard lỗi chặn liên hệ chủ động.

Hoàn thành bản đầu khi lõi và API adapter chạy được với adapter kiểm thử, lưu và phục hồi phiên được, và các tiêu chí hành vi bên dưới có bằng chứng. Demo HTTP tích hợp, gửi tin thật và thực thi action chỉ được gọi là hoàn thành sau khi nối platform thật. Fixture dùng cho kiểm thử thuật toán không được trình bày như world data trong demo.

## Dữ liệu và quyền thấy

Lõi dùng Python 3.11+, dataclass, enum và các types dùng chung hiện có. Các kiểu riêng của A1 ở `care_truc`, không copy enum contract.

Context nội bộ mang `run_id`, cutoff nghiệp vụ có timezone, principal đã xác thực, assessment, thông tin giá trị hàng từ platform, và trạng thái guard. Trường `source`, `proactive`, quyền sở hữu đơn, thời gian và danh tính khách không lấy trực tiếp từ payload client.

Mỗi lượt chỉ dùng assessment đã công bố với `assessed_at <= cutoff`. Contact phải khớp order và assessment ban đầu. Tại mỗi lượt mới, A1 có thể nhận assessment mới đã hoàn tất và lưu định danh đã dùng. Không trộn fields từ nhiều assessment. ETA không có thì nói chưa xác định; không dùng ngày cam kết làm ETA thay thế.

Người triển khai chọn giới hạn tuổi assessment 30 phút cho bản đầu, bằng một tick. Tuổi tính bằng cutoff nghiệp vụ trừ `assessed_at`. Đúng 30 phút còn hợp lệ; hơn 30 phút không dùng để mở contact chủ động hoặc xét xu, dù feed và heartbeat hiện tại còn tốt. Với inbound, A1 có thể nhắc facts cũ kèm thời điểm cập nhật và nói rõ chưa xác nhận tình trạng hiện tại. Không phát biểu ETA cũ như dự báo hiện tại. Context mới hợp lệ mới cho phép xét tiếp nghiệp vụ. Giới hạn này là policy A1, không thay ngưỡng freshness nguồn của D3.

A1 không truy vấn release DB. Platform cung cấp dữ liệu as-of. Thời gian nghiệp vụ do platform cấp, không lấy giờ máy để quyết định đơn replay trễ bao lâu. Wire dùng UTC ISO 8601; ngày cam kết được diễn đạt theo Asia/Ho_Chi_Minh.

Nếu thiếu hoặc sai context, A1 không tạo action. A1 vẫn cho phép tiếp nhận nhu cầu gặp người nếu principal hợp lệ. Assessment không hợp lệ phải trả lỗi có cấu trúc, không tạo `on_track` giả. Guard xấu không tự đóng mọi chat inbound, nhưng các facts không còn đáng tin phải được diễn đạt là thông tin chưa xác nhận và không làm căn cứ cấp xu.

## Trạng thái hội thoại

Phiên có `active`, `awaiting_cancel_confirmation`, `handoff_pending`, `transferred`, hoặc `completed`. Trạng thái pending gửi nằm trong contact và do adapter platform xác nhận. Không ghi một contact thành đã gửi chỉ vì tạo được nội dung.

Mỗi phiên lưu contact, chủ đơn, channel, nguồn mở phiên, assessment dùng cho mỗi lượt, messages, `turn_count`, `abusive_turn_count`, pending cancellation, và kết quả action đã biết. Một lượt là một message khách mới được chấp nhận; lời mở đầu không tăng bộ đếm. Retry cùng message không tăng lượt hoặc đếm chửi.

Chỉ xử lý một mutation mỗi phiên tại một thời điểm. Mỗi message có client request ID, được scope theo principal và phiên. ID lặp với cùng nội dung trả đúng kết quả trước. ID lặp với nội dung khác trả conflict.

Với `max_turns=8`, lượt thứ 8 kết thúc bằng bàn giao thay vì mở thêm quy trình hành động. Yêu cầu gặp người luôn có hiệu lực ngay cả khi cùng message có chửi hoặc đề nghị hủy. Lượt chửi thứ 3 dẫn đến bàn giao. Sau handoff_pending, transferred hoặc completed, không sinh action tự động mới. Message cũ retry vẫn trả kết quả cũ.

Intent chính dùng đúng các giá trị contract. Không coi thứ tự khai báo `INTENTS` là lệnh bỏ qua yêu cầu gặp người. Bộ đếm abuse độc lập với intent chính. Negation và lời trích dẫn phải được xét trước khi keyword tạo yêu cầu, ví dụ "tôi không muốn hủy" và "tài xế bảo tôi hủy".

`want_more` bao gồm yêu cầu hỗ trợ thêm. Eligibility xu còn cần cờ yêu cầu xu rõ ràng từ text hiện tại, không suy từ mọi `want_more`. Câu mơ hồ dẫn tới câu hỏi làm rõ, không tạo hành động tài chính. Rules có ví dụ tiếng Việt có dấu và không dấu. LLM tùy chọn không được tự biến câu mơ hồ thành quyền hủy hoặc quyền tiền.

## Bằng chứng và phản hồi

Lời mở đầu nêu tình trạng đã biết, ngày cam kết, ETA nếu có, và lời xin lỗi ngắn. Khách có thể hỏi nguyên nhân hoặc gặp người mà không phải dùng đúng một câu mẫu.

Mỗi phản hồi có customer text, intent, assessment reference, evidence references, decision codes, và action references nếu có. API nội bộ dành cho nhân viên có thể xem decision trace. Phần trả khách chỉ chứa bằng chứng được phép công khai. Không lộ tên tài xế, số điện thoại, ghi chú nội bộ, hoặc text thô không cần thiết.

Reason code có mapping rõ ràng tới template và evidence được cho phép. Code lạ dùng câu trung tính "chưa đủ thông tin để xác nhận nguyên nhân". A1 không suy lý do chi tiết từ free text. Thông tin tài xế chỉ là dữ liệu; không thay `fault_party` A2. Customer text và driver text không trở thành chỉ thị hệ thống.

Mặc định render mẫu bằng code. Adapter LLM tùy chọn chỉ chọn các đoạn diễn đạt đã duyệt theo ID và các slot facts được cung cấp. Renderer gắn facts sau cùng; LLM không viết tự do amount, ngày, ETA hoặc lời hứa. Response sai schema, ID lạ, slot lạ, text tự do, timeout hoặc lỗi provider đều dùng mẫu an toàn và ghi lý do. Một yêu cầu rephrase dạng text từ adapter cũ chỉ được chấp nhận nếu trùng một biến thể được renderer cho phép.

Đây là lựa chọn triển khai nhằm kiểm được lời hứa bằng code. Viết lại tự do với semantic validator không nằm trong bản đầu. Khi chưa cấu hình adapter LLM, toàn bộ luồng vẫn hoạt động bằng mẫu và API ghi rõ `template` là nguồn phản hồi.

## Kiểm guard và freshness

Platform cung cấp snapshot guard có identity, thời điểm heartbeat A3, feed health và controls. A1 không tin boolean `allowed` do client gửi. Thiếu guard, sai A3 identity, heartbeat tương lai, thiếu feed bắt buộc, hoặc timestamp nguồn tương lai đều chặn chủ động.

Heartbeat thiếu hoặc cũ hơn 60 phút, feed stale theo timestamp nguồn quá 30 phút, feed corrupt hoặc missing, và controls chặn đều cấm mở hoặc gửi liên hệ chủ động. Đúng 30 phút và 60 phút chưa vượt ngưỡng. Danh sách feed bắt buộc do adapter platform cung cấp từ policy server, không lấy từ client.

Gate kiểm lúc chuẩn bị contact và ngay trước platform dispatch. Snapshot chuẩn bị không phải giấy phép gửi sau này. Adapter platform phải kết hợp kiểm control mới nhất với quyết định dispatch. A1 trả trạng thái blocked nếu thiếu adapter kiểm này; không gọi gửi trực tiếp để né gate. A1 không tự nới controls khi dữ liệu phục hồi.

## Yêu cầu xu

Chỉ tạo `Action(kind="coins", source="a1")` khi toàn bộ điều kiện sau có bằng chứng server:

- Phiên chat hiện tại thật sự do A1 mở và contact chủ động đã được gửi thành công.
- Yêu cầu hiện tại là text do khách gửi, thể hiện rõ mong muốn nhận xu hoặc bồi thường xu. Lời dẫn, transcript voice, ticket cũ và câu hỏi về policy không đủ.
- Assessment hiện tại có `late_days >= 2`, đã được phép thấy và các facts cần thiết còn đáng tin. `unknown_feed`, thiếu kết luận bên chịu lỗi, hoặc `fault_party="unknown"` dẫn tới chưa đủ thông tin và không gửi tiền trong bản đầu.
- `fault_party` là carrier hoặc platform, không phải customer hoặc force_majeure.
- Chưa có grant cho order trong ledger platform và chưa có yêu cầu xu còn chờ của cùng order.

Code gọi `late_xu_for(items_value_vnd)` để tính quote. `None` hoặc 0 dùng mức sàn theo hàm contract; dữ liệu sai kiểu hoặc âm bị từ chối. LLM không quyết số tiền. Executor platform kiểm lại toàn bộ nghiệp vụ, amount, permissions và tính duy nhất trước thực thi.

Key xu ổn định theo run và order, không tạo key mới khi khách gửi lại bằng message ID khác hoặc mở phiên khác. Platform phải có UNIQUE order cho grant. Check eligibility trước ở A1 không thay transaction chống grant trùng của platform.

`Action.evidence_ref` trỏ tới bản ghi bền chứa contact, message khách, assessment và kết quả eligibility. Dùng queue `care`, `needs_approval=False` theo quy trình xu đã đủ điều kiện, nhưng executor vẫn là cổng quyền bắt buộc và có thể yêu cầu review theo controls. Thiếu executor không tự ghi ledger hoặc giả grant. Phản hồi chỉ nói đã gửi yêu cầu khi platform xác nhận nhận yêu cầu bền. Chỉ nói đã cấp sau receipt succeeded có thẩm quyền.

## Hủy và xác nhận lần hai

Khi khách muốn hủy, tạo pending request, giải thích đây là yêu cầu chờ xử lý, rồi yêu cầu xác nhận lại. Không hứa hoàn tiền hoặc hủy thành công.

Pending request có ID không đoán được, đúng principal, order, contact, phiên bản và thời hạn 10 phút theo đồng hồ nghiệp vụ. Thời hạn này là mặc định người triển khai đề xuất. Một yêu cầu mới thay thế pending cũ; khách đổi ý hoặc chuyển người sẽ vô hiệu pending.

API confirm cần request ID hiện hành và thao tác confirm rõ ràng của khách. Text "đồng ý" chỉ được hiểu là xác nhận khi gắn với đúng pending hiện hành và message trả lời bước xác nhận. Câu "đồng ý" ở ngữ cảnh khác không đủ. Khi hết hạn phải hỏi xác nhận lại, không tự gia hạn.

Sau xác nhận, A1 tạo một `cancel_request` amount 0, source a1, `confirmation_id` đúng request, `needs_approval=True`, queue `cancel_review`. Retry confirm trả cùng yêu cầu. Platform kiểm ownership và confirmation một lần nữa; nhân viên quyết định xử lý hủy và khoản tiền liên quan.

## Chuyển nhân viên

Trigger gồm yêu cầu rõ ràng của khách, chửi đủ 3 lượt, đạt giới hạn lượt, hoặc thiếu dữ liệu khiến A1 không thể xử lý nhu cầu hiện tại an toàn. Với câu hỏi thông thường thiếu ETA, A1 có thể trả lời giới hạn thông tin trước, không bắt buộc tạo handoff ngay.

Bản bàn giao render bằng code từ state, gồm order, lý do, nhu cầu khách, facts và evidence references, action với trạng thái receipt đã biết, pending cancellation còn hiệu lực hoặc đã vô hiệu, và việc cần người quyết định. Lời khách được gắn nhãn là lời khách, không biến thành fact logistics.

Mỗi phiên có một handoff đang mở. Retry không tạo bản sao. Khi tạo yêu cầu, phiên vào handoff_pending và A1 ngừng quyết định hành động mới. Chỉ chuyển trạng thái transferred và nói "đã chuyển yêu cầu" sau khi adapter nhận bền. Nếu queue lỗi, giữ pending delivery, báo chưa chuyển thành công và cho phép retry. Không hứa thời gian nhân viên phản hồi khi platform chưa có thông tin đó.

## Lưu phiên, adapter và API

Lõi A1 không phụ thuộc framework HTTP hoặc SDK provider. Các adapter hẹp gồm session store, assessment/context reader, guard/dispatch gate, action gateway, handoff sink, và optional phrase selector. Tên class và chữ ký cụ thể thuộc kế hoạch triển khai.

Bản đầu có SQLite session store riêng do A1 quản lý tại `runs/<run_id>/care.sqlite`. Chỉ tạo bảng A1 trong DB riêng, không sửa shared schema hoặc shared runtime DB. Transaction lưu message, trạng thái, pending intents gửi đi và response cùng nhau. Sau commit mới gọi platform. Retry dùng key ổn định; không giữ transaction mở khi chờ mạng hoặc LLM. Bảng pending delivery giúp gửi lại sau restart và giữ trạng thái chưa biết khi timeout.

Người triển khai chọn response POST bất biến. Với lượt sinh side effect, response đã commit chỉ xác nhận A1 đã ghi nhận yêu cầu tại local và trạng thái `pending_delivery`; không nói đã gửi hoặc đã thực thi. Ví dụ: "Mình đã ghi nhận yêu cầu hỗ trợ của bạn. Hiện chưa có xác nhận cấp xu." Retry message trả lại đúng response này kể cả receipt đã cập nhật. Dispatcher lưu receipt và thêm system event riêng có ID ổn định cho từng chuyển trạng thái. `GET /api/chats/{id}/messages` trả lịch sử gồm các system event và delivery status hiện tại để client thấy đã gửi, đang chờ đối soát, bị chặn, hoặc succeeded. Client bản đầu poll GET; chưa cần websocket. Retry receipt không thêm event trùng. Response thông thường không có side effect trả nội dung hoàn chỉnh ngay.

Platform action gateway phải nhận lặp cùng key một cách idempotent và cho tra receipt. Mất response sau khi platform có thể đã nhận không được coi là failed chắc chắn. Khi chưa thể đối soát, giữ pending hoặc unknown và không tuyên bố action thành công. Không đạt đúng một lần bên ngoài chỉ nhờ SQLite local.

API adapter nhận JSON và trusted request context từ server Huy. Client không được tự tạo trusted context. Adapter chạy được in-process và có contract tests. Việc mount HTTP, xác thực user, kiểm quyền sở hữu và transport là trách nhiệm platform. Mọi handler từ chối nếu không có principal đã xác thực. Staff endpoints cần quyền staff.

| Route dự kiến | Chức năng A1 |
| --- | --- |
| `POST /api/chats` | Mở phiên với order đã được xác thực. Client mở luôn là customer-initiated. Proactive chỉ từ platform nội bộ. |
| `GET /api/chats/{id}/messages` | Đọc lịch sử được phép thấy. |
| `POST /api/chats/{id}/messages` | Xử lý lượt có message ID, text và optional reply-to. |
| `POST /api/orders/{id}/cancel-requests` | Chuẩn bị yêu cầu hủy chờ xác nhận. |
| `POST /api/cancel-requests/{id}/confirm` | Xác nhận đúng pending request. |
| `POST /api/chats/{id}/handoff` | Gửi yêu cầu chuyển nhân viên, có request ID. |
| `GET /api/handoffs` | Staff đọc bản bàn giao. |
| `GET /api/chats/{id}/decisions` | Staff xem evidence references và lý do chặn hoặc fallback. Đây là route đề xuất thêm, cần Huy duyệt khi mount. |

Các tên route theo team plan, trừ decisions là đề xuất bổ sung. HTTP status mapping gồm 400 payload sai, 401 chưa xác thực, 403 không có quyền, 404 tài nguyên không thấy được, 409 request ID hoặc state conflict, và 503 adapter bắt buộc chưa sẵn sàng. Domain refusal như chưa đủ điều kiện xu trả response nghiệp vụ có decision code, không giả lỗi hệ thống. Không đưa chi tiết nội bộ hoặc secrets vào response khách.

Chưa có adapter platform thật thì test và demo lõi dùng adapter trong bộ nhớ có nhãn rõ ràng. Không thêm fake executor làm đường production mặc định. Không công bố các route đã hoạt động qua HTTP trước khi ghép server Huy.

## Kiểm chứng và quyền sở hữu

Test A1 tự kiểm nằm trong `care_truc/tests/`. Huy giữ `acceptance_truc/`; Trúc không sửa hoặc làm yếu test của Huy. Test chéo A2 sau đó nằm trong `acceptance_an_nguyen/`, là phần việc riêng, không chặn thiết kế lõi A1.

Các kiểm tra bắt buộc cho bản đầu gồm:

- 7 intent, phủ định, lời trích dẫn, tiếng Việt có dấu và không dấu, và human request đồng thời có chửi.
- Lượt 3 abuse, lượt 8 tổng, retry message không tăng bộ đếm, và phiên kết thúc không sinh action mới.
- Unknown reason, ETA None, ngày cam kết không đổi, và evidence không rò dữ liệu nội bộ.
- LLM trả date, amount, lời hứa, ID lạ, hoặc timeout đều fallback, không đổi action.
- Guard thiếu, heartbeat 60 phút và hơn 60 phút, feed 30 phút và hơn 30 phút, control đổi trước dispatch, và timestamp tương lai.
- Assessment đúng 30 phút và hơn 30 phút, kể cả khi feed và heartbeat mới nhưng A2 chưa cập nhật.
- D4 đúng và sai từng điều kiện, yêu cầu mơ hồ, customer-initiated chat, voice transcript, unknown fault, pending grant, retry liên phiên, và amount sai kiểu.
- Hủy phải xác nhận lại, nhầm principal hoặc order, request cũ, reply-to sai, hết hạn, đổi ý và confirm lặp.
- Handoff có ngữ cảnh, sink lỗi không báo thành công, và retry chỉ có một bản.
- Restart sau lưu message, sau ghi pending delivery, và sau gateway có thể đã nhận nhưng chưa có receipt.
- POST retry trả response bất biến, GET cho thấy receipt mới, và system event không trùng sau dispatch hoặc restart.
- API phân quyền, từ chối trường client giả mạo, lỗi có cấu trúc và không lộ trace cho khách.

Sau triển khai chạy import contracts, tests A1, toàn bộ pytest, `git diff --check`, và guardrails hiện có. Không cài hook. Chỉ gọi integrated demo đã kiểm chứng khi dùng assessment, guard và executor thật. Nêu riêng những adapter và voice chưa được ghép.

## Các việc cần ghép với Huy

Huy cung cấp context/principal đã xác thực, guard có feed policy và dispatch gate, giá trị hàng as-of, kho assessment, action gateway có receipt/idempotency, handoff sink và mounting HTTP. Người triển khai A1 có thể hoàn tất lõi với adapter tests trước; không tự sửa `contracts/`, dependencies, `platform_huy/` hoặc `acceptance_truc/`.

Web voice được thiết kế tiếp sau khi chọn provider và session negotiation. Khi ghép voice, mọi transcript giữ channel `web_voice`, không biến thành text request D4. Việc chuyển sang chat chỉ có hiệu lực theo nguồn mở phiên và yêu cầu text thực tế của phiên đó. Bản đầu không tuyên bố voice đã hoàn thành.

## Điều người dùng cần duyệt

Duyệt phạm vi chat trước và web voice sau, renderer với biến thể có kiểm soát thay cho rephrase tự do, API adapter chờ Huy mount HTTP, SQLite state riêng của A1, tuổi assessment tối đa 30 phút, response POST bất biến kèm GET cập nhật receipt, và thời hạn xác nhận hủy mặc định 10 phút. Thiết kế này không thay D1–D5 hay quyền sở hữu trong repo.

## Kết quả kiểm tra thiết kế

Reviewer đã đọc bản đầu và nêu hai câu hỏi về tuổi assessment và response sau dispatch. Bản này đã ghi lựa chọn của người triển khai: assessment tối đa 30 phút, POST trả acknowledgment bất biến và GET đọc receipt cùng system events. Không có thay đổi contracts hoặc quyết định D1–D5 từ lần kiểm tra này.
