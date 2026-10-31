# Spec harness riêng của Agent 1

Ngày: 2026-10-31. Trạng thái: đề xuất để duyệt, chưa có implementation.
Owner: Trúc. Phạm vi code tương lai: `care_truc/`. Nhánh hiện tại: `truc/agent-care`.

## 1. Mục đích và quan hệ với spec nghiệp vụ

Harness là runtime chạy A1: nhận sự kiện, nạp context và memory, thực hiện một lượt có giới hạn, kiểm kết quả, lưu bền, gửi yêu cầu và đối soát receipt. Harness cung cấp các điểm kiểm trước và sau model hoặc hành động, cùng dấu vết để kiểm chứng.

Spec này tách phần runtime khỏi [spec nghiệp vụ A1](2026-10-31-agent-care.md). Các intent, điều kiện xu, hủy và chuyển người do policy nghiệp vụ quyết định. Harness bảo đảm policy đó chạy đúng thứ tự, không bị bỏ qua và phục hồi được sau lỗi. Hai spec đều đang chờ duyệt; tài liệu này không tự biến đề xuất cũ thành quyết định đã được người dùng chấp thuận.

Nguồn bắt buộc là [AGENTS.md](../../AGENTS.md), [team plan](../../docs/team_plan.md), [D1–D5](../../docs/decisions.md), [types](../../contracts/types.py) và [params](../../contracts/params.py). Nếu đề xuất runtime mâu thuẫn nguồn bắt buộc, nguồn bắt buộc thắng và cần sửa spec trước triển khai.

## 2. Lựa chọn cho bản đầu

Các lựa chọn dưới đây là mặc định người viết đề xuất:

- Python 3.11+, standard library và pytest đang có. Lõi không phụ thuộc SDK model hoặc workflow framework.
- Loop cố định, tối đa một lần gọi model mỗi lượt. Model chỉ chọn biến thể diễn đạt được duyệt; không có vòng tự gọi tool.
- Một tiến trình A1 hoạt động cho mỗi `run_id`. Các phiên có thể chờ I/O đồng thời nhưng một phiên chỉ xử lý một lượt tại một thời điểm.
- SQLite riêng tại `runs/<run_id>/care.sqlite` làm memory bền và hàng chờ gửi. Không dùng vector database, memory dùng chung giữa khách, hoặc LLM summary làm nguồn sự thật.
- Hooks runtime là các điểm mở rộng có kiểu dữ liệu rõ ràng trong code, được cấu hình khi khởi động. Chưa có plugin động hoặc script do khách tải lên.
- Bản đầu xử lý chat. Giữ nguồn `web_voice` trong kiểu dữ liệu để từ chối quyền xu đúng D4, nhưng chưa cung cấp voice transport.

Harness không lập lịch replay, không thay thứ tự A3 → A2 → A1, không đọc DB nguồn, không sở hữu HTTP server, không cài Git hooks, và không thực thi tiền. Những phần này vẫn thuộc platform hoặc quy trình repo.

## 3. Các thành phần và ranh giới

| Thành phần đề xuất | Trách nhiệm |
| --- | --- |
| `CareHarness` | Điều phối tiếp nhận sự kiện, xử lý lượt, đọc trạng thái, drain và recovery. |
| `CarePolicy` | Hàm nghiệp vụ thuần: state và facts vào, state dự kiến và effect proposals ra. Không truy cập mạng hoặc ghi DB. |
| `ContextProvider` | Cấp principal, quyền sở hữu, cutoff, assessment và guard từ platform đã xác thực. |
| `MemoryStore` | Transactions, request deduplication, phiên, events, pending effects và schema version. |
| `PhraseSelector` | Model adapter tùy chọn, chỉ trả ID biến thể trong tập cho phép. |
| `ResponseRenderer` | Gắn facts bằng code và tạo response hoặc tóm tắt bàn giao theo policy. |
| `Guardrails` | Kiểm input, context, model output, proposals và quyền gửi. |
| `EffectDispatcher` | Gửi effect đã commit qua platform và đối soát receipt. |
| `RuntimeHooks` | Quan sát hoặc siết quyết định tại các điểm vòng đời đã định nghĩa. |

Tên file, class phụ và cách chia module được để cho người triển khai. Không tạo generic agent framework để dùng cho A2 hoặc A3. Không copy `Action`, `OrderAssessment`, `ContactTask`, các enum, hoặc params sang bộ định nghĩa khác.

## 4. Đầu vào và API nội bộ

Các thao tác sau là interface đề xuất, không phải hàm hoặc endpoint đã tồn tại:

| Thao tác | Đầu vào và kết quả |
| --- | --- |
| `open_chat` | Order ID, request ID và trusted context khách, tạo phiên customer-initiated; không tự nâng thành proactive. |
| `open_contact` | ContactTask và trusted context từ platform, trả contact pending hoặc blocked. |
| `handle_message` | Session ID, message ID, text, optional reply-to và trusted request context, trả response hoặc trạng thái processing. |
| `confirm_cancel` | Pending confirmation ID, request ID và trusted context, đi qua cùng runtime và idempotency như message. |
| `request_handoff` | Session ID, request ID và trusted context, đi qua cùng runtime, không có đường tắt ghi queue. |
| `get_messages` | Trả lịch sử công khai và delivery status sau kiểm ownership. |
| `get_trace` | Trả decision trace đã lọc cho staff có quyền. |
| `drain_pending` | Xử lý batch effects đến hạn, có giới hạn kích thước và thời gian. Chỉ platform gọi. |
| `recover` | Kiểm schema, phục hồi lượt gián đoạn và đối soát effects sau restart. Chỉ runtime gọi. |
| `get_health` | Trả readiness, trạng thái adapters và số effects chờ hoặc cần đối soát cho platform, không lộ nội dung chat. |

API adapter A1 ánh xạ các route chat, xác nhận hủy, handoff và decision trace đã đề xuất trong spec nghiệp vụ tới các thao tác này. Huy mount vào server, cấp principal và thực thi auth. Health, drain và recovery không trở thành public mutation endpoints. Mỗi thao tác đọc vẫn kiểm quyền, kể cả retry đã có cache.

Trusted context là object nội bộ do server tạo, không parse từ các field `role`, `source`, `proactive`, `guard_allowed`, `cutoff` hoặc `amount` do client tự gửi. Payload có field giả mạo quyền bị từ chối; không âm thầm dùng field đó. Không có generic endpoint nhận arbitrary Action từ model hoặc khách.

Envelope lưu `run_id`, session/contact/order IDs, request ID, principal reference, channel và nguồn mở phiên. Phiên gắn với một chủ đơn và một order. Model không sửa các định danh này. Hệ thống phân biệt raw customer text, structured facts, driver text và server instructions.

Mở phiên và lời mở đầu không tăng turn_count. Message, confirm_cancel và request_handoff từ khách là các customer events; mỗi event mới tăng một lượt khi final commit. Button xác nhận được lưu như typed event, không biến thành text request D4. Các API dùng chung namespace request ID trong phiên và không có đường bỏ qua max_turns hoặc đếm hai lần cùng event. Ở lượt thứ 8, handoff thay mọi action tiền hoặc xác nhận hủy chưa gửi. Yêu cầu gặp người vẫn được ghi nhận khi phiên đã handoff_pending, theo cùng handoff key.

Thời gian nghiệp vụ dùng UTC có timezone do platform cung cấp. Timeout và backoff runtime dùng đồng hồ vận hành, không dùng cutoff replay. Đổi giờ replay không làm timeout mạng chạy nhanh hoặc làm lease vận hành hết hạn.

## 5. Loop xử lý một lượt

Mỗi lượt có các phase cố định, ghi phase vào trace mà không ghi suy luận nội bộ của model:

1. Xác thực principal, ownership, channel, schema và giới hạn input. Từ chối input sai trước khi tạo công việc có side effect.
2. Kiểm request ID. Cùng ID và cùng payload đã commit trả response cũ. Cùng ID nhưng payload khác trả conflict. Request processing có task còn sống trả `processing`, không tạo task model thứ hai. Request không còn owner task hoặc đến hạn retry_wait được tiếp tục theo quy tắc phục hồi trong mục 11.
3. Giữ quyền xử lý riêng của phiên. Lượt khác đang chạy trong cùng phiên trả `session_busy` để client retry, không giành state hoặc xếp vô hạn trong RAM.
4. Lưu request mới ở phase `processing`, fingerprint payload và state version gốc. Nạp một context snapshot đầy đủ. Context lookup lỗi vẫn có thể tạo kết quả giới hạn thông tin hoặc handoff theo policy khi ownership đã được xác thực.
5. Chạy rules để xác định intent, bộ đếm, giới hạn lượt và policy outcome. `ask_human`, abuse lần 3 và lượt thứ 8 được xử lý trước bước model. Rules quyết action proposals và confirmation; model không thay quyết định này.
6. Lập model context giới hạn và chạy `before_model`. Nếu có phrase selector, đủ budget và không có veto, reserve model attempt bền rồi gọi adapter đúng một lần.
7. Kiểm schema và ID của model output, chạy `after_model`, chọn biến thể hợp lệ hoặc fallback. Không yêu cầu model tự sửa câu trả lời qua một vòng lặp mới.
8. Render text bằng facts đã chọn. Chạy toàn bộ output và proposal guardrails. Response an toàn vẫn phải kiểm kể cả khi dùng template hoặc model đã bị bỏ qua.
9. Commit nguyên tử state mới, bộ đếm, response cuối bất biến, events, evidence bundle và pending effects. Đánh dấu request `committed` và tăng session version một lần.
10. Trả response đã commit và nhả quyền xử lý phiên. Việc gửi effects diễn ra sau transaction, qua dispatcher. Client đọc receipt mới bằng GET.

Với lượt sinh side effect, response chỉ xác nhận đã ghi nhận local và có `pending_delivery`. `committed` không có nghĩa yêu cầu đã tới platform hoặc tiền đã được cấp. Với lượt chỉ giải thích, response trả đầy đủ ngay. Khi request đã committed, mọi retry trả đúng response đó; receipt mới xuất hiện dưới system events và delivery status.

`processing` không phải response cuối được cache vĩnh viễn. Request có các phase processing, retry_wait, committed và failed_terminal. Nếu store lỗi hoặc không thể commit, không trả success, không gửi effect và không tăng bộ đếm. Trước commit, state nghiệp vụ mới chỉ là kết quả dự kiến.

Không chờ tick 30 phút để trả lời một message. Tick chỉ cấp assessment mới và contact tasks. Hội thoại dùng context đã công bố và guard phù hợp tại thời điểm xử lý.

## 6. Giới hạn và điều kiện dừng

| Giới hạn | Mặc định đề xuất | Khi chạm giới hạn |
| --- | --- | --- |
| Lượt khách trong phiên | `contracts.params.max_turns`, hiện là 8 | Lượt thứ 8 tạo handoff; không mở quy trình tiền hoặc hủy mới. |
| Lượt chửi | 3 lượt khách khác nhau | Tạo handoff, không đếm lại khi retry. |
| Text mỗi message | 4.000 Unicode code points | Trả input error, không tăng lượt. Không cắt text trước xét intent. |
| Model calls mỗi lượt | 1 attempt, kể cả sau restart | Bỏ model hoặc fallback. |
| Model context | 12.000 UTF-8 bytes sau serialize | Bớt lịch sử từ cũ nhất; nếu phần bắt buộc vẫn vượt thì bỏ model. |
| Model output | 2.048 UTF-8 bytes | Từ chối output và fallback. |
| Model timeout | 3 giây vận hành | Hủy chờ và fallback; bỏ mọi callback đến muộn. |
| Context hoặc gateway call timeout | 2 giây mỗi call | Context suy giảm hoặc giữ pending/unknown; không giả receipt. |
| Retry submission mỗi effect | Tối đa 3 calls có thể đã ra ngoài | Sau hết budget, yêu cầu đối soát; không tạo key mới. |
| Backoff vận hành | 1 giây rồi 5 giây giữa các lần gửi | Chờ trong hàng bền, không sleep trong transaction. |
| Một batch drain | Tối đa 20 effects hoặc 2 giây để bắt đầu effect mới | Nhường quyền; không bắt đầu effect tiếp theo khi hết budget. |

Mỗi call đã bắt đầu có timeout riêng; budget drain không bảo đảm batch kết thúc đúng 2 giây. Adapter mạng phải hỗ trợ deadline và cancellation. Không chạy lời gọi blocking không có timeout trên event loop. Adapter không thực thi được hợp đồng deadline thì không được cấu hình làm adapter runtime sẵn sàng.

Token hoặc chi phí model chưa có ngưỡng tiền vì chưa chọn provider. Giới hạn calls, bytes và timeout áp dụng ngay cả khi provider không trả token usage. Nếu có usage thì lưu metadata, không ước tính thành chi phí như số đo thật.

## 7. Memory bền và context model

Memory chia thành ba phần có quyền ghi rõ ràng:

- Lịch sử hội thoại append-only, gồm message khách, phản hồi và system events. Lưu channel và nguồn text thực tế cho từng message.
- State có cấu trúc: session status, counters, assessment reference, pending cancellation, handoff và delivery status. Chỉ policy và renderer từ facts server được phép cập nhật các fields của mình.
- Facts logistics snapshot và evidence bundle cho từng quyết định. Assessment mới thay snapshot cho lượt mới, không sửa bằng chứng của lượt đã commit.

Không dùng summary do LLM viết để xác nhận lỗi, điều kiện xu, nguồn mở phiên hoặc xác nhận hủy. Handoff summary render từ state. Không có trí nhớ lâu dài giữa các khách. Bản đầu giữ dữ liệu theo run, chưa có tác vụ tự xóa theo ngày; production retention policy cần thiết kế riêng trước vận hành ngoài demo.

Model chỉ nhận intent đã xác định, allowed phrase IDs, các facts công khai cần thiết và tối đa 4 lượt gần nhất nếu còn budget. Instructions cố định nằm riêng với dữ liệu khách. Bỏ nội dung cũ khỏi prompt không xóa memory và không xóa counters hoặc pending confirmation. Không nạp raw driver notes, PII nội bộ, API keys, DB paths hoặc toàn bộ ledger vào prompt.

Assessment reference gồm order ID, assessed_at và hash canonical của đầy đủ assessment. Kiểm evidence nhìn thấy được tại cutoff. Giới hạn tuổi assessment 30 phút và confirmation TTL 10 phút là đề xuất kế thừa từ spec nghiệp vụ, chưa phải shared params mới.

Các bảng A1 dự kiến chỉ nằm trong DB riêng:

| Nhóm bảng | Nội dung và ràng buộc cần có |
| --- | --- |
| `runtime_meta` | Schema version và boot generation; từ chối version không hỗ trợ, không reset DB để né migration. |
| `sessions` | Identity, nguồn mở, channel, policy status, counters và state version. |
| `requests` | UNIQUE theo run, principal, session và request ID; payload hash, phase, context snapshot, model attempts và final response. |
| `events` | Event ID, session sequence, visibility, nội dung message cần lưu và trace metadata. UNIQUE sequence trong phiên. |
| `pending_effects` | Stable effect ID/key, typed payload, evidence reference, transport state, attempt count, next attempt time và bound session version. |
| `effect_proposals` | Các revision append-only trước lần gửi đầu, source request và context/evidence reference. Một revision hiện hành cho mỗi effect. |
| `effect_attempts` | Dấu vết bắt đầu call đã commit trước network, deadline, attempt ID và kết quả nếu đã biết. |
| `receipts` | Receipt có thẩm quyền, effect ID, remote reference, revision và execution outcome. Receipt lặp không tạo event mới. |

Một request có thể sinh nhiều records nhưng các thay đổi quyết định nghiệp vụ commit cùng transaction. SQL constraints chống duplicate; lock RAM không thay UNIQUE constraints. Chỉ `MemoryStore` ghi DB A1. Không mở transaction trong lúc gọi mạng hoặc model.

`evidence_ref` của Action trỏ tới bundle bền do A1 sở hữu. Platform cần adapter đọc bundle đó theo quyền server để kiểm D4. Nếu chưa có cách platform resolve reference, effect tương ứng bị blocked vì thiếu adapter; không gửi một chuỗi tham chiếu mà executor không kiểm được.

## 8. Hooks runtime

Hooks dưới đây khác Git pre-commit hoặc pre-push. Đây là callbacks trong vòng đời A1, chỉ code server đã cấu hình mới đăng ký được.

| Hook | Được quan sát hoặc đề xuất | Giới hạn |
| --- | --- | --- |
| `on_input` | Metadata input đã xác thực, rate limit hoặc veto nghiệp vụ bổ sung | Không đổi principal, nguồn phiên hoặc raw text. |
| `before_model` | Context model đã lọc, budget và allowed phrase IDs | Có thể bỏ model; không thêm tools hoặc facts mới. |
| `after_model` | Kết quả parse, schema validation và metadata provider | Có thể từ chối output hoặc chọn fallback; không sửa outcome nghiệp vụ. |
| `before_action` | Proposal đã commit, eligibility và gate hiện tại | Có thể block thêm; không tạo proposal mới, tăng amount, bỏ approval hoặc mở quyền. |
| `after_action` | Receipt và trạng thái sau commit | Chỉ quan sát; không biến accepted thành succeeded. |
| `on_error` | Phase, error code và metadata đã lọc | Chỉ quan sát; không nuốt lỗi rồi cho action chạy. |

Hooks là async callbacks có input bất biến và kết quả kiểu `continue`, `veto` hoặc `use_fallback` ở nơi cho phép. Observer hooks không có kết quả điều khiển. Tổng timeout của các hooks trong một phase là 100 ms vận hành. Registry cố định khi khởi động, chạy theo thứ tự cấu hình và không cho callback tự đăng ký callback khác trong lượt.

Core guardrails luôn chạy, dù registry rỗng. Veto không thể được hook sau đó đảo ngược. Kết quả hook phải qua schema validation. Exception hoặc timeout tại `on_input` tạo kết quả blocked an toàn; tại model hooks dùng template; tại `before_action` chặn gửi. Lỗi `after_action` hoặc `on_error` được ghi như lỗi quan sát, không rollback receipt đã commit hoặc gửi effect lại.

Hooks không tự gọi model, gateway hoặc shell. Harness không cung cấp capability đó trong hook context. Đây là quy ước cho code server được tin cậy, không phải sandbox bảo mật chống Python code độc hại. Thay đổi registry cần phiên bản cấu hình và restart runtime.

## 9. Guardrails bắt buộc

| Ranh giới | Kiểm tra |
| --- | --- |
| Input và quyền | Auth context, ownership, payload, channel, request ID và giả mạo quyền từ client. |
| Context | Đúng order, cutoff hợp lệ, không tương lai, assessment snapshot nhất quán, facts có nguồn và tuổi assessment. |
| Policy | Rules trước LLM; max_turns, abuse, ask_human, xác nhận hủy đúng pending, D4 và `late_xu_for`. |
| Model | Chỉ allowed phrase IDs, schema và bytes hợp lệ. Text tự do, ID lạ, tool call hoặc lời hứa lạ dẫn tới fallback. |
| Output | Renderer giữ nguyên facts, amount, dates và promises; customer view không lộ evidence nội bộ hoặc trace staff. |
| Trước gửi | Proposal chưa bị vô hiệu, permissions mới nhất, approval cần thiết và guard A3 cho contact chủ động. |
| Receipt | Nguồn server, effect/key/payload đúng, revision hợp lệ và transition không hạ trạng thái đã biết. |

Proactive dispatch bị chặn khi heartbeat A3 thiếu hoặc quá 60 phút; feed bắt buộc stale quá 30 phút theo timestamp nguồn, corrupt hoặc missing; control không cho phép; timestamp tương lai; hoặc adapter gate thiếu. Danh sách feed bắt buộc thuộc policy server. Đúng 30 và 60 phút chưa vượt ngưỡng. A1 không nới control sau khi nguồn hồi phục.

Đối với tiền, chỉ A1 gửi Action request. `source` lấy từ server, amount tính bằng luật, eligibility D4 và một lần mỗi order do executor kiểm lại. Receipt accepted chưa phải cấp xu. Transcript voice không thành yêu cầu text hợp lệ. Guard lỗi không tự đóng inbound hoặc ngăn ghi nhận yêu cầu gặp người.

Việc kiểm trước gửi ở local không thay kiểm nguyên tử tại cổng platform. Nếu permissions hoặc control đổi sau bước chuẩn bị, gateway kiểm lại trước nhận hoặc dispatch. Không quảng cáo cơ chế thu hồi được tin nhắn đã tới provider.

## 10. Effects, retry và receipt

Harness chỉ có ba loại effect nội bộ: `contact_send`, `action_request` và `handoff_request`. `action_request` mang nguyên Action contract. Các loại còn lại là envelope riêng của A1, không thêm ActionKind vào contracts. Model không chọn effect type hoặc tham số effect.

Key được tạo bằng code từ định danh ổn định: contact key từ ContactTask, coins key từ run và order, cancel key từ pending confirmation ID, handoff key từ run và session. Effect retry giữ nguyên key và payload. Attempt ID khác nhau nhưng không trở thành idempotency key mới. UNIQUE key xu local và executor ledger kiểm trùng qua nhiều phiên cùng order; nếu dùng nhiều run cùng nghiệp vụ, executor vẫn phải bảo đảm once-per-order trong phạm vi tài khoản thật.

Người viết chọn cho phép thay proposal bị blocked trước khi bắt đầu bất kỳ outbound attempt nào. Một yêu cầu text mới, rõ ràng của khách với context hợp lệ có thể tạo proposal revision mới cho cùng coins effect/key. Revision cũ giữ nguyên bằng chứng, revision mới có payload và evidence mới; không có hai revision được dispatch đồng thời. Model hoặc worker không tự mở lại proposal. Kiểm và thay revision nằm trong transaction theo effect key để chống hai phiên cùng order đua nhau.

Sau khi đã reserve bất kỳ attempt có thể ra ngoài, key và payload bị đóng băng. Không thay amount hoặc evidence rồi dùng lại key đó. Nếu outcome chưa biết thì chỉ đối soát hoặc retry chính payload cũ khi còn đủ quyền. Nếu bị từ chối hoặc không thể dùng lại payload cũ, A1 chuyển nhân viên để platform đánh giá tiếp, không tạo key xu khác nhằm đi vòng. Đây là giới hạn bảo thủ của bản đầu, không phải quy tắc rằng một lần bị từ chối đồng nghĩa đã được cấp xu.

Transport state gồm `pending_delivery`, `in_flight`, `retry_wait`, `delivered`, `blocked` và `needs_reconciliation`. Execution outcome lưu riêng: unknown, accepted, awaiting_approval, succeeded hoặc rejected. `delivered` nghĩa platform nhận bền, không nghĩa effect nghiệp vụ đã thực thi. Với contact, quyền xét D4 còn cần receipt contact thực sự đã được gửi thành công, không chỉ queue accepted.

Dispatcher dùng cùng session lock với mutations hội thoại. Core guards và `before_action` chạy trên snapshot trước transaction claim. Sau đó transaction so sánh lại session version và effect revision hiện hành; nếu khác thì bỏ claim và đánh giá lại, không gửi dựa trên snapshot cũ. Nếu vẫn hợp lệ, dispatcher commit `in_flight`, attempt, bound revision và call budget trước network. Không giữ transaction trong lúc chạy hook, và không giữ transaction hoặc session lock trong lúc gọi mạng. Claim của coins effect còn phải kiểm UNIQUE theo effect key khi được chia sẻ qua nhiều phiên.

Commit in_flight là mốc A1 coi yêu cầu đã bắt đầu chuyển và không còn bảo đảm vô hiệu local. Nếu khách đổi ý hoặc handoff commit trước mốc này, pending effect bị blocked và không gọi network. Nếu tới sau mốc này, A1 ghi nhận mong muốn mới và chuyển người khi cần, nhưng nói rõ yêu cầu trước đang gửi hoặc chờ kết quả; không báo đã thu hồi. Quyền platform/A3 vẫn phải được kiểm tại gateway và có thể chặn việc gửi. Việc local đã claim không phải giấy phép bỏ qua gate đó.

Effect đã delivered không gửi lại; chỉ tra receipt. Nếu đã in_flight nhưng mất kết quả, vào needs_reconciliation trước khi quyết định gọi lại. Nếu context hoặc state mới không còn cho phép submit payload cũ thì chỉ lookup và bàn giao, không retry submit. Không cần giữ khóa DB qua network để giải quyết race khách đổi ý.

Timeout có thể xảy ra sau khi remote đã nhận. Harness tra receipt theo stable key trước. Chỉ retry submit khi adapter xác nhận idempotency cho cùng key và payload, đồng thời vẫn đủ business permissions. Unknown không được đổi thành rejected chỉ vì đã chờ lâu. Khi hết 3 submission attempts hoặc adapter thiếu lookup, giữ needs_reconciliation và ghi việc cần người xử lý. Không retry business refusal hoặc permission denial.

Mỗi lượt drain đối soát tối đa một lookup cho mỗi effect tới hạn. Lookup timeout áp dụng backoff 1 giây rồi 5 giây; tối đa 3 lookup calls tự động liên tiếp không có kết quả có thẩm quyền trước khi cần người tiếp tục đối soát. Không có endpoint cho khách hoặc LLM tự xóa budget. Nhân viên có thể yêu cầu platform kiểm tra, nhưng việc đó không tạo quyền tiền mới.

Receipt cùng effect có revision tăng do adapter platform cấp. Revision lặp cùng nội dung là no-op; cùng revision khác nội dung báo lỗi adapter; revision cũ không ghi đè trạng thái mới. Receipt terminal không đổi sang terminal mâu thuẫn. Nếu platform chưa có revision, adapter phải đưa ra một hợp đồng tương đương được kiểm thử trước khi sẵn sàng.

System event được deduplicate theo effect và receipt revision. Cancel chỉ đổi sang chờ reviewer, không báo đã hủy. Handoff chuyển từ handoff_pending sang transferred sau durable acknowledgment. Contact mở không ghi sent khi provider chỉ mới nhận vào queue. Không gửi text cho khách công bố succeeded từ một exception hoặc trạng thái không biết.

## 11. Restart và đồng thời

Một `run_id` chỉ có một runtime A1 giữ process lock của OS. Lock được giải phóng khi process chết. Khởi động process thứ hai cùng run phải thất bại rõ ràng, không chạy hai dispatcher cùng DB. Cách cài OS lock dùng standard library theo nền tảng thuộc người triển khai; không dựa duy nhất vào file lock không có owner hoặc không được giải phóng.

Trong process, mỗi session có một lock ngắn cho cả lượt. Các phiên khác vẫn chạy khi một phiên chờ model. SQLite có một nơi ghi, transaction ngắn; không chia connection không an toàn giữa threads. Hook hoặc model callback phải mang request ID, state version và boot generation. Callback đến muộn không được ghi response, tăng counters hoặc tạo effect sau khi lượt đã fallback hoặc boot đã đổi.

Lock phiên bao phủ một lượt đang xử lý, còn dispatcher chỉ giữ cùng lock trong giai đoạn kiểm và claim ngắn. Quyền owner task nằm trong registry runtime. `finally` gỡ owner khi task chết hoặc bị hủy. Lỗi tạm trước final commit ghi retry_wait nếu store còn hoạt động; nếu store lỗi thì row processing có thể còn, nhưng không được giả là task còn sống.

Client retry cùng request ID hoặc recovery worker có thể tiếp tục request không còn owner trong cùng process, sau khi lấy session lock. Dùng lại payload đã lưu, giữ model-attempt budget, nạp state đã commit hiện hành và context mới. Không hồi sinh kết quả dự kiến chưa commit. Tối đa 3 lần xử lý request trước final commit, ghi processing-attempt counter bền trước mỗi lần; backoff 1 giây rồi 5 giây vận hành. Nếu chưa thể lưu counter thì không bắt đầu xử lý lại.

Lỗi invariant hoặc lỗi policy không dự kiến kết thúc request ở failed_terminal; hết processing budget cũng như vậy. Không tăng turn_count hoặc tạo effect từ request failed_terminal. Retry cùng ID trả cùng error code cuối, không chạy lại. Nếu schema/payload sai ngay ở ingress thì chưa tạo request nghiệp vụ. Store mất kết nối chưa ghi được kết quả cuối trả service error; khi store phục hồi, owner detection và processing counter bảo đảm request không kẹt vĩnh viễn hoặc reset budget.

Recovery chạy trước readiness:

1. Mở đúng DB A1 và kiểm schema version, transaction consistency và process lock. DB corrupt hoặc version không hỗ trợ làm runtime không ready; không tạo DB mới đè lên.
2. Tăng boot generation. Tìm requests processing chưa có final commit. Những request này chưa được phép có outbound effect.
3. Nạp lại state đã commit cuối và context server hiện hành để xử lý request gián đoạn. Không dùng snapshot cũ để tự mở quyền mới. Nếu model attempt đã reserve thì fallback, không gọi lần thứ hai.
4. Xác định effects pending hoặc retry_wait đến hạn. Effects in_flight không có receipt phải đối soát trước. Effects delivered tiếp tục tra outcome nếu cần.
5. Commit response hoặc trạng thái recovery, rồi bật readiness khi store và dispatcher đã phân loại được công việc còn lại. Có effects needs_reconciliation không ngăn inbound nếu store và quyền đọc hợp lệ.

Lỗi hoặc crash trước final commit không tăng turn_count. Crash sau commit không tạo turn mới khi retry. Crash sau khi remote nhận được xử lý bằng idempotency và lookup. Không khẳng định exactly-once cho side effects chỉ nhờ local SQLite.

Khi shutdown, runtime dừng nhận mutation mới, ngừng bắt đầu effects và chờ tối đa 5 giây vận hành cho việc đang chạy. Sau thời hạn, hủy chờ có thể hủy được và giữ pending hoặc in_flight để recovery. Không phát sinh effect mới trong `on_error` hoặc shutdown handler.

## 12. Trace, health và cách kiểm chứng

Mỗi quyết định có `trace_id`, run/session/request references, phase, policy và template versions, context/assessment reference, hook outcomes, guard decision codes, model source, elapsed runtime và effect references. Ghi response source là template hoặc model-selected. Trace không lưu chain-of-thought, secrets, raw provider prompts hoặc raw driver notes.

Customer API chỉ trả nội dung được phép công khai và trạng thái yêu cầu của khách. Staff có thể xem decision codes như `guard_missing`, `assessment_stale`, `model_output_rejected`, `cancel_confirmation_expired`, `effect_unknown` và `hook_failed`. Store evidence và trace bắt buộc lỗi thì mutation không được coi là commit thành công. Log quan sát bên ngoài lỗi thì giảm health, nhưng không sửa receipt hoặc lặp effect đã commit.

Health phân biệt `ready`, `degraded` và `not_ready`. Không có model adapter là degraded với khả năng dùng template, không tự chặn chat. Không có gateway hoặc gate bắt buộc thì chặn effect tương ứng. Không có store, process lock hoặc auth/context adapter cần thiết thì not_ready. Health không giả tạo heartbeat A3.

Harness có bộ adapter kiểm thử trong `care_truc/tests/`, không làm production defaults. Test dùng fake monotonic clock, trusted context cố định và gateway scripted receipts để chủ động tái hiện timeout, lỗi và restart. Fixtures phục vụ thuật toán; không ghi vào release DB hoặc đưa vào replay như world data.

Không cần provider thật để chứng minh loop, memory và recovery. Kiểm thử với provider, HTTP server, A3/A2 và executor thật là integration riêng. Kết quả phải ghi rõ adapter nào đang được thay bằng fixture.

## 13. Tiêu chí nghiệm thu

| Nhóm | Hành vi phải chứng minh |
| --- | --- |
| Loop | Mỗi message mới commit một lượt; rules trước model; request đang processing không gọi model thêm; phiên khác không bị kẹt theo model. |
| Budgets | Một model attempt qua restart; timeout fallback; callback muộn bị bỏ; input/context/output quá giới hạn xử lý đúng. |
| Memory | Restart giữ lịch sử, counters và pending confirmation; cắt prompt không xóa state; summary không mở quyền nghiệp vụ. |
| Hooks | Thứ tự cố định; core guards vẫn chạy khi không có hook; veto không bị đảo; lỗi từng hook có kết quả đã quy định. |
| Output | Model trả ngày, tiền, tool call hoặc ID lạ bị loại; template vẫn qua validator; không lộ PII hoặc trace staff. |
| Guard | Heartbeat và feed đúng ngưỡng hoặc vượt ngưỡng; stale assessment; timestamp tương lai; control đổi trước dispatch. |
| Quyền | Sai principal/order bị từ chối ở mutation, GET và retry; payload giả source không trở thành quyền. |
| Idempotency | Cùng ID cùng payload trả kết quả cũ; khác payload conflict; xu nhiều phiên cùng order không tạo yêu cầu mới. |
| Persistence | Lỗi commit không gửi effects; crash trước commit không tăng lượt; crash sau commit không lặp quyết định. |
| Effects | Remote accepted rồi timeout không báo succeeded; retry cùng key; lookup và submission hết budget đi đối soát; receipt cũ không ghi đè. |
| Revision | Proposal chưa từng gửi có thể được thay bởi yêu cầu mới; revision cũ không dispatch; đã reserve attempt thì payload và key bất biến. |
| Hủy và handoff | Xác nhận đúng pending; đổi ý vô hiệu effect chưa gửi; handoff pending ngăn action mới; thất bại queue không báo đã chuyển. |
| Race và phục hồi tại chỗ | Đổi ý trước claim chặn network; đổi ý sau claim không báo thu hồi; request mất owner được resume cùng process mà không gọi model quá budget. |
| Vận hành | Process thứ hai cùng run bị từ chối; DB lỗi không reset; shutdown/restart giữ công việc chưa biết. |

Unit và integration tests của harness nằm trong `care_truc/tests/`. Không sửa `acceptance_truc/` của Huy để làm xanh. Khi triển khai, chạy import contracts, tests harness, toàn bộ pytest, diff check và guardrails repo. Các lệnh chạy harness thực tế được ghi sau khi có entry point, không trình bày lệnh chưa tồn tại như tính năng đã chạy.

## 14. Phụ thuộc platform và phần để người triển khai quyết

Huy cung cấp authenticated principal, ownership lookup, business clock, assessment/guard snapshots, feed policy, gate dispatch, giá trị hàng as-of, evidence resolver, gateway idempotent có receipt lookup và handoff sink. Trúc cung cấp harness cùng API adapter, không tự sửa contracts, dependencies, platform hoặc test acceptance của Huy.

Nếu một adapter chưa có, A1 vẫn chứng minh được runtime với test adapter có nhãn. Production không tự fallback sang fake gateway. Protocol adapter cần được Huy duyệt trước tích hợp HTTP hoặc gửi thật, nhưng không chặn viết lõi và tests theo spec đã duyệt.

Người triển khai tự quyết tên module, SQL chi tiết/indexes, primitive khóa OS, cách chạy async I/O với SQLite và cấu trúc test helpers. Mọi lựa chọn phải giữ các invariant, budgets, phân quyền và tiêu chí nghiệm thu ở trên. Chọn provider, SDK hoặc thêm shared dependency cần phối hợp Huy; không thuộc quyết định ngầm của spec harness.

## 15. Trạng thái bàn giao

Tài liệu này chỉ đặc tả harness. Viết xong spec không có nghĩa loop, memory, hooks hoặc guardrails nghiệp vụ đã được setup. Bước tiếp theo sau khi duyệt thiết kế là viết implementation plan cùng tên trong `.scratch/plans/2026-10-31-agent-care-harness.md`, rồi triển khai và kiểm chứng từng phần.

Reviewer đã đọc bản đầu và hỏi về race trước gửi, phục hồi request ngay trong process và proposal bị chặn. Bản bàn giao đã ghi rõ mốc claim in_flight, request ownership cùng processing budget, và quy tắc revision trước khi gửi. Đây là lựa chọn của người viết, cần được duyệt cùng thiết kế.
