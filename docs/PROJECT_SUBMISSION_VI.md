# SEA OpenAI — Hệ thống đa agent hỗ trợ xử lý đơn giao trễ

**Nhóm thực hiện:** Huy, An Nguyên, Trúc

**Bối cảnh:** Hackathon Shopee × OpenAI, thời gian triển khai 7 giờ

**Ngày cập nhật:** 31/10/2026

**Phạm vi:** Bản mẫu trình diễn trên dữ liệu tổng hợp; không kết nối hệ thống giao dịch thật của Shopee.

## 1. Bài toán và mục tiêu

Khi một đơn hàng có nguy cơ giao trễ, khách hàng cần biết đơn đang ở đâu, ngày nào dự kiến nhận được và vì sao bị chậm. Đội vận hành đồng thời phải phân biệt sự cố vận chuyển với dữ liệu cập nhật muộn, tránh thông báo sai hoặc đưa ra cam kết thiếu căn cứ.

Dự án tách bài toán thành ba nhiệm vụ: **kiểm tra độ tin cậy của dữ liệu, đánh giá tình trạng đơn hàng và chăm sóc khách hàng**. Mỗi kết luận phải gắn với thời điểm quan sát và bằng chứng; các hành động nhạy cảm phải qua kiểm tra quyền và điều kiện nghiệp vụ.

Mục tiêu demo là trình bày một quy trình có thể giải thích và kiểm tra lại: từ sự kiện logistics đến đánh giá đơn, thông tin khách nhận được và lịch sử xử lý. Nhóm không đặt mục tiêu chứng minh hiệu quả kinh doanh trên dữ liệu thực trong thời gian hackathon.

## 2. Dữ liệu được chuẩn bị như thế nào?

### 2.1. Nguồn gốc và khai báo

Theo tài liệu nguồn `data/release_main/DATA.md`, bộ dữ liệu được đội chuẩn bị trước ngày thi bằng script Python với seed cố định. Đây là dữ liệu **tổng hợp**, mô phỏng sàn thương mại điện tử hư cấu “Chợ Phố”; khách hàng, đơn hàng, doanh nghiệp và hãng vận chuyển không phải các thực thể thật.

Dữ liệu mô phỏng mạng lưới giao nhận, hành trình kiện hàng, lần giao thất bại, hoàn trả, lịch sử bồi thường và vận hành hệ thống. Một số cấu trúc được tham khảo từ nghiệp vụ thương mại điện tử Việt Nam; các tỷ lệ và tham số mô phỏng là giả định, không đại diện cho thống kê nội bộ Shopee.

Tài liệu nguồn khai báo các câu ticket ban đầu được tạo bằng Claude, sau đó script điền thông tin thuộc chính bộ dữ liệu tổng hợp và thêm biến thể ngôn ngữ. Dữ liệu có chủ ý chứa nội dung đối kháng để kiểm tra việc agent coi văn bản khách hàng là dữ liệu, không phải lệnh điều khiển.

**Phân biệt hai giai đoạn:** dữ liệu đã được tạo trước cuộc thi; ứng dụng trong demo chỉ phát lại bộ dữ liệu đó, không sinh thêm sự kiện thế giới để làm đẹp kết quả. Script sinh dữ liệu không nằm trong repository giải pháp hiện tại.

### 2.2. Bộ dữ liệu sử dụng trong demo

Hai cơ sở dữ liệu SQLite chính nằm tại `data/release_main/`:

| Tệp | Vai trò | Dung lượng xấp xỉ |
| --- | --- | ---: |
| `core_14d.sqlite` | Đơn hàng, vận chuyển, giao hàng, hoàn trả, ticket và lịch sử bồi thường | 67,6 MB |
| `ops_14d.sqlite` | Chỉ số hệ thống, log, cảnh báo và webhook | 29,5 MB |

Lát dữ liệu gồm các đơn tạo từ **18–31/10/2026**. Sự kiện liên quan tiếp tục đến **08/11/2026** để có kết cục của các đơn cuối kỳ. Vì vậy, “14 ngày” là cửa sổ tạo đơn, không phải giới hạn thời gian của mọi bảng.

Số lượng dưới đây được kiểm lại trực tiếp bằng truy vấn chỉ đọc trên hai tệp:

| Nhóm dữ liệu | Số bản ghi |
| --- | ---: |
| Đơn hàng | 14.687 |
| Kiện hàng | 13.543 |
| Sự kiện quét hành trình | 125.827 |
| Lần giao hàng | 15.011 |
| Hoàn trả | 522 |
| Ticket chăm sóc khách hàng | 535 |
| Bồi thường lịch sử | 2.701 |
| Chỉ số vận hành | 291.456 |
| Log vận hành | 11.607 |
| Cảnh báo | 44 |
| Webhook nhận từ hãng vận chuyển | 36.874 |

Bộ `data/tiny/` phục vụ thử đường đọc và xử lý thiếu dữ liệu. Bộ nhỏ thiếu ngày cam kết và telemetry vận hành, nên không được dùng thay bản release để chứng minh toàn bộ luồng demo.

### 2.3. Kiểm định và bảo toàn dữ liệu

Nhóm đã sao chép release và tiny vào thư mục dữ liệu của dự án, kiểm tra SHA-256, cấu trúc SQLite, trường thời gian và các liên kết nghiệp vụ. Hai tệp release có hash khớp manifest; `PRAGMA quick_check` trả về `ok`. Dữ liệu nguồn được mở ở chế độ chỉ đọc.

Một số đặc điểm quan trọng từ kiểm định:

- Release có ngày cam kết hợp lệ cho toàn bộ 14.687 đơn. Giá trị hàng từ 6.500 đến 20.154.000 đồng.
- Có sự kiện nhận muộn, bản ghi trùng và nhiều dòng cùng thời điểm ingestion; replay phải xử lý chúng mà không bỏ mất dòng hoặc sửa nguồn.
- Có 1.115 dòng bồi thường lịch sử không tìm thấy đơn tương ứng trong lát dữ liệu. Đây là giới hạn của lát cắt, không được âm thầm coi là lịch sử khách hàng đầy đủ.
- Thống kê hồi cứu ghi nhận 1.126 đơn giao sau ngày cam kết trong nhóm đã có scan giao thành công; 277 đơn trễ ít nhất hai ngày. Đây **không phải** danh sách mặc nhiên được nhận bồi thường tại một tick.

Trạng thái phiên chat, nhịp tim agent, quyết định của nhân viên và quyền lợi mới được ghi vào SQLite runtime riêng. StateStore chỉ có bản SQLite, không sử dụng MongoDB. Khi triển khai trên Space, runtime nằm trên đĩa local; nhóm chấp nhận trở về baseline sau khi Space restart, không yêu cầu giữ trạng thái qua lần restart đó. Trong một phiên chạy vẫn phải bảo đảm giao dịch và không cấp trùng. Không sửa `sim_clock`, nội dung hay schema của DB nguồn. Dữ liệu, runtime và `.env` không được đưa lên Git.

## 3. Replay theo thời gian, không nhìn trước kết quả

Người trình diễn bấm **NEXT**, mỗi lần tăng đồng hồ mô phỏng đúng **30 phút**. Chat xử lý tại thời điểm mô phỏng hiện tại; giờ máy chủ chỉ phục vụ ghi log.

Một sự kiện có hai mốc cần phân biệt:

- `event_at`: lúc sự kiện xảy ra ngoài vận hành.
- `ingested_at`: lúc hệ thống nhận được bản ghi.

Ví dụ, một scan xảy ra lúc 10:00 nhưng đến 10:40 mới được nhận thì không được dùng trong đánh giá lúc 10:30. Cursor scan dựa trên `ingested_at`; các bảng không có cột này được lọc theo trường thời gian phù hợp của chính bảng. Các trường kết cục tương lai phải được che tại thời điểm replay.

Ứng dụng dùng `ReleaseReader` để đọc snapshot theo thời điểm, thay vì cập nhật đồng hồ trong DB nguồn. Bộ đáp án riêng không được đưa vào đầu vào agent. Các con số hồi cứu trong tài liệu này dùng để mô tả dữ liệu, không cấp cho agent như kiến thức về tương lai.

## 4. Kiến trúc ba agent

Luồng đích của hệ thống:

```text
NEXT (+30 phút) → Snapshot chỉ đọc → A3 kiểm tra dữ liệu
                                      ↓
                              A2 đánh giá từng đơn
                                      ↓
                          Danh sách đơn / UI / A1
                                      ↓
                     Khách phản hồi hoặc nhân viên xác minh
                                      ↓
                     Cổng thực thi → Biên nhận runtime
```

### A3 — Giám sát dữ liệu và điều kiện chủ động liên hệ

**Huy phụ trách.** A3 kiểm ba feed: đơn hàng, scan và lần giao; trả về `trusted`, `stale`, `corrupt` hoặc `missing`. Độ cũ tính từ timestamp nguồn đến tick hiện tại; quá 30 phút là stale. Việc hệ thống vừa nhận lại dữ liệu không làm timestamp nguồn mới hơn.

A3 ghi nhịp tim mỗi lượt chạy. Theo cấu hình demo đã chốt, nhịp tim thiếu hoặc quá **90 phút** chặn liên hệ chủ động. Nút **Kill A3** chặn ngay và ngừng ghi nhịp; **Revive** cho phép ghi nhịp mới ở tick tiếp theo. Chỉ mở lại khi feed đạt điều kiện và không còn lệnh chặn áp dụng. A3 chỉ siết chính sách, không tự gỡ `proactive_block`, không cấp tiền.

### A2 — Đánh giá logistics và giải thích bằng chứng

**An Nguyên phụ trách.** A2 gắn mỗi đơn đúng một nhãn theo thứ tự ưu tiên:

`exception → unknown_feed → customer_fault → late → at_risk → watch → slow_safe → on_track`

Ngày trễ dựa trên `guaranteed_date`, kết thúc lúc **23:59:59 theo giờ Việt Nam**. Chậm vài giờ nhưng vẫn trong ngày cam kết chưa được tính là giao trễ. ETA mới không thay thế ngày cam kết gốc.

A2 bàn giao mã đơn, ngày đặt, mốc bàn giao vận chuyển, ngày cam kết, ETA mới, nguyên nhân, độ tin cậy và bằng chứng. Thiếu thông tin thì giữ trạng thái chưa xác định hoặc tạo câu hỏi cho người giám sát. Văn bản tự do của tài xế không được tự thay đổi bên chịu lỗi. A2 không thực thi quyền lợi tài chính.

### A1 — Chăm sóc khách hàng có giới hạn

**Trúc phụ trách**, cùng UI và API. Thiết kế ưu tiên nhận diện ý định bằng luật, trả lời theo dữ kiện A2 và template được kiểm soát. Vai trò LLM bị giới hạn; không tự quyết tiền, ngày giao hoặc lời hứa. Nội dung sinh ra phải qua kiểm tra trước khi sử dụng.

A1 cần hỏi xác nhận lại trước yêu cầu hủy; chuyển nhân viên khi khách yêu cầu hoặc có ba lượt xúc phạm; giới hạn số lượt tự xử lý. Kênh thoại thuộc phạm vi web voice, không gọi số điện thoại. Bản hiện tại đã có nền hội thoại, lưu phiên, hàng đợi xử lý và cơ chế phục hồi; tích hợp HTTP, vận chuyển tin nhắn và voice còn là phần công việc tiếp theo.

## 5. Quyền lợi và quyền thực thi trong demo

Đây là **chính sách do nhóm đặt cho mô phỏng**, không phải tuyên bố về chính sách hiện hành của Shopee.

- **Xu:** 5% giá trị hàng, làm tròn xuống bội 1.000; tối thiểu 10.000, tối đa 1.000.000.
- **Voucher:** giá trị 10.000 đồng, tách riêng với xu.
- Cùng điều kiện xét: trễ ít nhất hai ngày lịch Việt Nam, không do lỗi khách hoặc bất khả kháng, khách chủ động xin bằng text trong chat do A1 mở. Voice không cấp quyền lợi này.
- Mỗi loại tối đa một lần trên một đơn, dùng hai khóa riêng `xu:{order_id}` và `voucher:{order_id}`. Lần từ chối vẫn lưu audit nhưng chưa khóa quyền xét lại; lần đã cấp phải trả lại biên nhận cũ khi retry.
- Khi thiếu bằng chứng về lỗi hoặc bất khả kháng, nhân viên có thể xác minh và lưu quyết định có audit; không được bỏ qua các điều kiện khác.

Thiết kế dành một cổng `execute_action` của platform để kiểm quyền và ghi tác động. A1 gửi yêu cầu; A2, A3 và LLM không tự ghi tiền. Quyền lợi chỉ tồn tại trong runtime nội bộ, không cộng ví hoặc phát voucher Shopee thật. Cổng thực thi đầy đủ vẫn đang được hoàn thiện.

Đối với hoàn trả nhiều lần, phạm vi đề xuất là hiển thị số lần có bằng chứng thuộc shop để shop tự đánh giá, không kết luận khách gian lận.

## 6. Những gì đã có và phần đang tích hợp

Tình trạng đối chiếu với bản A1/A2 trên main tại commit `82c4398` và quyết định gỡ tích hợp MongoDB sau đó, ngày 31/10/2026:

| Thành phần | Tình trạng |
| --- | --- |
| Dữ liệu release và kiểm định | Đã có; hash và số lượng bảng chính được kiểm lại khi soạn tài liệu |
| Hợp đồng dữ liệu và nền SQLite runtime | Đã có types, schema, tham số và migration nền |
| A3 | Đã có feed health, heartbeat, kill/revive và gate liên hệ chủ động |
| Giao diện demo A3 | Đã nối NEXT và API A3; đã kiểm tra HTTP/trình duyệt trên release, phần chăm sóc hiện là bản nháp minh họa |
| A2 | Đã có replay, đánh giá, ETA baseline, câu hỏi giám sát và payload bàn giao UI |
| A1 | Đã vào main: luật hội thoại, template, xác nhận hủy, handoff, SQLite lưu phiên, hàng đợi/phục hồi và API nội bộ Python |
| Luồng ba agent hoàn chỉnh | Đang tích hợp adapter, ngưỡng guard, khóa chống cấp trùng và biên nhận hành động |
| HTTP chat, UI khách/shop, voice và thực thi quyền lợi | Chưa được xác nhận chạy xuyên suốt với dữ liệu release |

Nhóm đã có kiểm thử đơn vị, acceptance, biên thời gian, xử lý retry và kiểm tra A3 bằng dữ liệu release. Sau khi gỡ tích hợp MongoDB và các test riêng của tích hợp đó, kiểm tra trong môi trường sạch không cài PyMongo cho kết quả **518 acceptance test và 96 test A1 đạt, không có test lỗi hoặc bị bỏ qua**. Các test A1 dùng adapter kiểm thử được ghi rõ; chúng không chứng minh đã gửi tin thật hoặc cấp quyền lợi qua platform. Nhóm chưa công bố accuracy ETA, tỷ lệ giảm hủy đơn hay hiệu quả chăm sóc trên dữ liệu thực.

## 7. Kịch bản trình diễn

**Phần đã kiểm chứng:** mở giao diện A3, tăng tick, quan sát độ tin feed và nhịp tim; tắt A3 rồi NEXT hai lần để thấy liên hệ chủ động bị chặn; bật lại và chạy tick mới để kiểm tra phục hồi có điều kiện. Đối chiếu hash sau chạy để chứng minh DB nguồn không đổi.

**Luồng đích sau khi hoàn tất tích hợp:** chọn một đơn từ dữ liệu release, xem mốc vận chuyển và lý do đánh giá từ A2; mở chat qua A1; thử hỏi lý do, yêu cầu gặp người hoặc xác nhận hủy. Với đơn đủ điều kiện và bằng chứng, thử xin xu/voucher rồi gửi lại yêu cầu để chứng minh không cấp trùng. Các bước này chỉ được báo hoàn thành sau kiểm thử toàn luồng.

## 8. Giá trị của giải pháp và giới hạn

Điểm chính của dự án là tách **độ tin dữ liệu**, **kết luận logistics** và **quyền hành động**. Nhờ đó, một câu trả lời hợp lý về ngôn ngữ chưa đủ để tạo cam kết hay tác động tài chính; hệ thống còn phải có dữ liệu đúng thời điểm, bằng chứng và quyền thực thi.

Bộ release đủ để phát triển các tình huống trễ, ngoại lệ vận chuyển, dữ liệu nhận muộn và giám sát agent. Tuy nhiên, đây vẫn là mô phỏng: lịch sử không đầy đủ cho mọi đơn, thiếu bằng chứng xác minh ở một số ca và chưa thay thế đánh giá thực tế. Nhóm giữ các giới hạn này hiển thị thay vì bổ sung dữ liệu giả vào replay.

**Tài liệu đối chiếu trong dự án:** `docs/data_audit.md`, `data/release_main/DATA.md`, `data/release_main/manifest.sha256`, `logistics_an_nguyen/README.md`, `care_truc/README.md` và `care_truc/VERIFICATION.md`. Dữ liệu nguồn được cung cấp riêng, không nằm trong Git. Các quy tắc demo trong tài liệu này phản ánh quyết định mới nhất của nhóm; một số tài liệu khung cũ còn ghi ngưỡng heartbeat 60 phút và cần được đồng bộ khi tích hợp.
