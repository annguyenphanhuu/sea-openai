# Rà soát main mới theo hướng demo-first — 31/10/2026

Phạm vi: chỉ đọc code/tài liệu, chỉ ghi báo cáo này; không chạy test, sửa code, sửa spec/plan hoặc thao tác Git. Revision `8361c5f` chứa upstream `1fd109e`/PR #7 là thông tin controller cung cấp, không được báo cáo này xác nhận bằng Git. Các đường dẫn/line dưới đây là nội dung working tree đã đọc. Đây là review và đề xuất, không phê duyệt policy còn thiếu hay cho phép bắt đầu draft plan.

## Kết luận để controller dùng

Main mới bổ sung nghiên cứu điều phối hữu ích, **chưa cung cấp runtime điều phối mới**. Chọn đường demo có thể quan sát: nguồn thật read-only → A3 và A2 committed → danh sách đơn/evidence → một phiên chat nhận lượt ngay giữa ticks → handoff hoặc hủy hai bước → quan sát guard chặn liên hệ khi lỗi. Sau đó thêm coins/voucher trong runtime SQLite theo policy Huy vừa xác nhận và cơ chế xác minh còn cần chốt. Tín hiệu lịch sử trả hàng là một lát cắt đọc độc lập, chỉ số đếm trong shop đang xem. Huy đã xác nhận **demo nội bộ runtime SQLite**, không có tiền/coupon/provider Shopee thật.

Nền Huy chạy được là điều kiện cần cho demo toàn dự án, chưa phải toàn bộ demo. A1/HTTP/auth/UI và web voice thuộc Trúc; Huy không tự viết thay. Nếu chỉ demo được Python foundation, phải gọi đúng phạm vi đó. Việc ưu tiên text trước voice là **đề xuất thứ tự**, không tự xóa yêu cầu voice khỏi mục tiêu toàn nhóm.

## 1. Sự thật hiện tại: code và nghiên cứu khác nhau

| Thành phần | Bằng chứng đã đọc | Kết luận hiện trạng |
| --- | --- | --- |
| A2 có Python API thực | `logistics_an_nguyen/service.py:20` serializer; `:67` evaluate_tick; `assessment.py:70`; `replay.py:25`; `progress.py:12`; `questions.py:13` | Có đánh giá, projection read-only, progress và lưu câu hỏi. Không tự cấp quyền gửi hay tiền. |
| Reader nguồn của A2 | `logistics_an_nguyen/replay.py:28–32`, `:43–63` | Đã dùng mode=ro/query_only và cutoff. Huy vẫn cần kiểm corruption/identity trước reader; SQL scan lọc cả event_at nên không đủ để phát hiện mọi visible corrupt row. |
| Guard dependency hiện có | `logistics_an_nguyen/models.py:94–101`; `assessment.py:85–99` | FeedHealth.usable_at kiểm freshness nguồn; A2 thiếu/bad health có reason/evidence suy giảm. Exception có ưu tiên trên unknown_feed (`assessment.py:164–176`), nên UI phải hiển thị health riêng, không suy trust từ status duy nhất. |
| Toàn batch A2 | `logistics_an_nguyen/service.py:74–87` | Tuple comprehension hiện không cô lập exception một order; không có per-order failure envelope hoặc batch publisher trong API này. |
| Platform/A3/executor | `platform_huy/README.md:2–5`; file listing hiện chỉ README, serve_ui và ui_prototype | Scaffold, chưa có execute_action hoặc coordinator thật. Các class/signature trong spec là thiết kế (`.scratch/specs/2026-10-31-huy-platform-design.md:86`). |
| A1 | `care_truc/README.md:2–5`; thư mục hiện chỉ README | Chưa có implementation A1 để Huy ghép hoặc acceptance thật. |
| UI | `platform_huy/ui_prototype/README.md:21–23`; `index.html:22`, `:42–43` | Fixture và state trong trang; nút handoff/clock không tạo side effect backend. Không dùng nó làm bằng chứng demo end-to-end. |
| Server hiện tại | `platform_huy/serve_ui.py:30–39` | Chỉ SimpleHTTPRequestHandler phục vụ file tĩnh, không phải API/chat server. |
| PR nghiên cứu orchestration | `.scratch/research/2026-10-31-agent-orchestration.md:3`, `:103`, `:178` | Tự ghi rõ không triển khai code, pseudocode không phải API, chưa benchmark/end-to-end. |

Không suy ra khả năng mới từ tên agent, dataclass, file nghiên cứu hay merge commit. Nghiên cứu chủ yếu làm rõ các seam cần xây; không chứng minh latency, retry hoặc failure recovery đã hoạt động.

## 2. Những gì phải cập nhật trước khi dùng spec/plan cho demo

### 2.1 Clock và chat giữa hai ticks

Nghiên cứu đề xuất xử lý tin nhắn ngay với assessment đã hoàn tất, không chạy lại toàn batch hoặc đợi tick sau (`.scratch/research/2026-10-31-agent-orchestration.md:55–69`). Spec đã có record_contact/message và tách proactive gate khỏi inbound (`.scratch/specs/2026-10-31-huy-platform-design.md:82`, `:188–197`) nhưng chưa có consumer xử lý lượt A1.

Điểm cần quyết định rõ: spec đóng băng business now ở checkpoint và từ chối event timestamp lớn hơn now (`.scratch/specs/2026-10-31-huy-platform-design.md:68–70`). Sau checkpoint 10:00, tin nhắn nhận lúc wall clock 10:17 có timestamp 10:17 sẽ bị validation_error; ma trận còn chủ động kiểm trường hợp này (`.scratch/specs/2026-10-31-huy-platform-design.md:301–302`). Nếu HTTP adapter lấy wall time làm created_at thì demo chat giữa ticks hỏng dù route phản hồi ngay. Khi A3/tick thất bại, checkpoint cũng không tiến nên tuổi heartbeat theo now đóng băng có thể không tăng; không được trông chờ tuổi >60 phút tự chặn sau lỗi đã biết. Cần failure signal/control riêng như mục 2.2.

**Đề xuất kỹ thuật để Huy/Trúc review:** giữ assessment cutoff/version tách khỏi thời gian nhận lượt; chọn rõ chế độ replay demo trước implementation. Nếu chọn freeze business clock, adapter server đóng dấu business event tại simulated_now và lưu received_at wall clock riêng để audit; không yêu cầu khách đợi tick và không sửa timestamp do khách gửi để cấp quyền. Nếu chọn replay clock liên tục thì phải sửa rule current-time, freshness và evidence revalidation cho phù hợp, không chỉ đổi một datetime. Cả hai đều cần spec/seam mới; báo cáo không chọn thay Huy. Timeout dùng monotonic runtime như nghiên cứu `:85`, không dùng clock replay để đếm timeout.

### 2.2 A3 lỗi một phần, incident và degraded result

Spec đã xử lý visible corruption/quarantine và cho order hợp lệ nhận unknown_feed (`.scratch/specs/2026-10-31-huy-platform-design.md:64–66`); đó là điểm phù hợp với nghiên cứu. Nhưng unsafe snapshot rollback toàn tick (`:64`, `:76`) và heartbeat/incident/control cùng transaction (`:31`) có nghĩa incident lỗi có thể bị rollback cùng output. Draft Task 4 hiện kiểm incidents cũng rỗng khi rollback và raise mọi exception khác (`.scratch/plans/2026-10-31-huy-platform.md:268–279`, `:315`). Đây là kiểm atomicity đúng cho success attempt, chưa có đường ghi failure vận hành.

Nghiên cứu yêu cầu không return mất incident, không heartbeat thành công giả; A3 timeout phải block proactive nhưng giữ inbound/handoff (`.scratch/research/2026-10-31-agent-orchestration.md:73–77`, `:108–115`, `:143–155`). Cần bổ sung đường failure riêng:

- A3 hoàn tất nhưng feed bad: commit actual health/heartbeat, sticky block và incident; A2 chạy với health bad nếu projection còn an toàn. Giữ nguyên priority statuses A2 và hiển thị health riêng.
- A3 timeout/exception hoặc snapshot không an toàn: không publish success tick hoặc watermark/progress mới; rollback attempt rồi ghi failure incident và proactive block bền trong transaction riêng nếu state DB còn dùng được. Heartbeat thành công cũ không đủ cho phép liên hệ sau failure đã biết. API vẫn nhận inbound/handoff với nhãn last-good assessment; không hứa ETA/tiền dựa trên facts hết trust.
- State DB không ghi được: trả trạng thái vận hành không khỏe và deny proactive tại live gate; không nói incident đã lưu. Có thể cần fallback phục hồi, không biến lỗi lưu trữ thành success.
- A2 lỗi một order: code hiện có chưa cô lập. Bản demo tối thiểu có thể fail batch, giữ batch cũ đã công bố và ghi failed order/incident riêng, hoặc bổ sung per-order outcome sau review với An Nguyen. Không tạo assessment thành công giả, không thêm status ngoài STATUSES và không publish batch pha hai versions.

Các ý trên là **đề xuất**, cần đưa vào spec và acceptance failure path. Không cần thêm framework queue/LLM orchestrator để giải quyết chúng.

### 2.3 Handoff, API và ranh giới gửi

Spec có handoff durable `(run_id,tick_at,order_id)`, a1_status=pending_integration và gate kiểm lại trước gửi (`.scratch/specs/2026-10-31-huy-platform-design.md:78–82`), phù hợp nghiên cứu batch publication (`.scratch/research/2026-10-31-agent-orchestration.md:81–85`). Chưa có API đọc StoredTick/assessment công khai trong signatures ngoài run_tick; chưa có phiên bản lượt chat, handoff record hay send claim/authorization boundary thật (`.scratch/specs/2026-10-31-huy-platform-design.md:177–215`). Không buộc chat/API gọi run_tick chỉ để đọc lại kết quả.

**Seam tối thiểu đề xuất:** Huy cung cấp read view committed có run_id/cutoff/checkpoint_version, assessment/health và failure hiện tại; Trúc đọc để render, serialize từng session, xử lý 7 intents theo rules rồi validator và lưu handoff thật. Trước mở/gửi proactive, Trúc gọi gate mới nhất; Huy xác định điểm authorization serialize với control update. Không giữ transaction SQLite trong lúc gọi LLM/provider. Retry lượt/handoff/contact dùng stable key và cùng request trả cùng kết quả.

Các route toàn nhóm đã là yêu cầu tại `docs/team_plan.md:69–88`; mỗi tính năng demo phải đi qua API thật của Trúc. Spec public cancel getter/recovery đã tương đối rõ (`.scratch/specs/2026-10-31-huy-platform-design.md:199–220`, `:269–273`) và nên tận dụng. Trusted ServerContext/origin/request signal không lấy từ body; rule explicit-text deterministic của Trúc còn là dependency thật (`.scratch/specs/2026-10-31-huy-platform-design.md:245–249`), không thay bằng fixture rule trong demo release.

### 2.4 Policy và trạng thái draft đang lệch xác nhận mới

Theo cập nhật mới nhất controller truyền từ Huy trong lần review này, đã chốt: coins 5%, floor 1.000, min 10.000/max 1.000.000, None/0→10.000; voucher mệnh giá 10.000 VND **và coins là hai loại độc lập, mỗi loại tối đa một lần/order**. Voucher dùng **cùng eligibility coins**: trễ ít nhất hai ngày lịch VN, khách yêu cầu text trong chat A1 đã mở, không lỗi khách, không bất khả kháng. Demo chỉ ghi runtime SQLite, không cấp tiền/voucher ra Shopee/provider thật. Cơ chế xác minh bằng chứng, clock/failure semantics và mapping source history vẫn cần làm rõ; không hỏi lại trigger voucher đã chốt.

Spec vừa di chuyển có banner DRAFT tại `.scratch/specs/2026-10-31-huy-platform-design.md:3` ghi nhận voucher+coins độc lập. Core cũ tại `.scratch/specs/2026-10-31-huy-platform-design.md:11–13` đã được đánh dấu historical; `:267` là baseline policy_not_configured, chưa phải extension issuance mới. Draft plan cũng ghi chưa được bắt đầu (`.scratch/plans/2026-10-31-huy-platform.md:13`, `:622`). Cần hoàn thiện extension theo policy còn thiếu rồi review phần đổi, không thi hành thẳng Task 1–9 như demo plan hoàn chỉnh.

`contracts/params.py:11–20` đã tính đúng số coins được xác nhận; không phải thay công thức. `contracts/schema_state.sql:53–68` chỉ ledger xu UNIQUE(order_id); voucher cần lưu vết riêng/once-kind và policy được duyệt, không ghi voucher vào amount_xu (`docs/team_plan.md:60`). Huy là người duy nhất chỉnh contracts/migration.

Decision log `.scratch/research/2026-10-31-huy-demo-decisions.md` ghi cách xử lý FM chưa biết còn phải hỏi; không gán unknown thành có hoặc không có FM. Cách block/review trong baseline spec chưa trở thành policy kinh doanh được Huy duyệt. Coins release-wide vẫn có blocker thực: chưa có rule/evidence chứng minh force majeure absent và history non-coins mapping (`.scratch/specs/2026-10-31-huy-platform-design.md:259`, `:327`). Voucher và coins độc lập loại bỏ suy diễn “có voucher thì mặc định cấm coins”; nó chưa tự giải nghĩa mọi legacy ledger source/kind hay chứng minh lịch sử đầy đủ. Không tự chọn “không có cảnh báo = absent”, không dùng carrier fault thay FM evidence, không gọi local ledger là tiền đã gửi ra ngoài.

## 3. Demo slices đề xuất theo thứ tự nhìn thấy được

| Slice | Người xem thấy gì | Điều kiện hoàn thành và giới hạn |
| --- | --- | --- |
| D0 — data → assessment | Chạy một tick release thật; danh sách đơn, guaranteed date/ETA nullable, reason/evidence, health/cutoff | Huy source/A3/state + A2 hiện có; Trúc API/UI. Nguồn read-only, output committed, retry tick không nhân progress. Không dùng fixture UI thay release records. |
| D1 — guard failure và chat tiếp tục | Feed bad/A3 failure chặn mở chat chủ động; phiên inbound/đang mở vẫn trả lời facts giới hạn và xin người được handoff | Huy durable failure/control + current gate; Trúc real chat/handoff API, session ordering. Đây là lát cắt chứng minh điều phối thay vì chỉ thêm dashboard. Fault injection ở harness/runtime riêng, không sửa DB nguồn. |
| D2 — cancel hai lượt | Request → khách xác nhận riêng → hàng chờ → reviewer approve/reject; refresh/retry giữ cùng workflow | Huy workflow/idempotency/getters; Trúc auth/UI/API và separate affirmative turn. Approval chỉ runtime review, chưa carrier cancellation/refund. |
| D3 — lịch sử trả hàng riêng shop | Shop xem count yêu cầu, distinct orders có yêu cầu, distinct physical returned scans, coverage/evidence | Huy read model; Trúc shop auth/API. Cross-shop bị từ chối, không score/verdict/threshold; count không đổi coins/fault. Có thể làm song song D2 sau source/auth seam. |
| D4 — coins và voucher | Text A1 hợp lệ → server quote + gate + receipt; coins và voucher10.000 ghi riêng trong runtime SQLite, mỗi loại once/order; retry không cấp lần hai | Eligibility hai loại đã chốt giống nhau. Positive release demo còn cần cơ chế xác minh facts/FM/history được Huy duyệt. Trước đó có thể chuẩn bị blocker/review và test fixture có nhãn; không gọi fixture là release-positive demo. Voice transcript không cấp coins; không có Shopee/provider effects. |

Web voice là slice Trúc riêng sau text seam, có API negotiation và handoff; chưa có code/provider trong tree. LLM rephrase chỉ sau rules/validator và fallback template. Đề xuất hoãn concurrency/graph framework/LLM orchestrator, không hoãn atomicity, authorization hoặc once/order. Slices này là đề xuất demo-first, chưa tự biến thành scope Huy phải viết A1/UI/voice.

Mỗi slice nên có một thao tác UI/API, một output thật và một negative case quan sát được; controller chỉ gọi hoàn thành phạm vi đã đi qua runtime. Acceptance A1 của Huy còn pending seam Trúc (`.scratch/specs/2026-10-31-huy-platform-design.md:327`), không mock executor hoặc skip để gọi pass.

## 4. Các câu còn cần Huy trả lời trước nhánh phụ thuộc

1. **Clock demo nội bộ:** Khi khách nhắn giữa hai tick, Huy muốn business clock giữ ở tick cuối và lưu giờ nhận thật riêng, hay chạy replay liên tục giữa ticks? Lựa chọn này quyết định timestamp chat, freshness và current evidence; không mặc định wall 10:17 hợp lệ sau tick10:00. Cần duyệt failure signal bền để A3 lỗi không dựa vào heartbeat aging trên clock bị đứng.
2. **Xác minh cho positive demo release:** Rule/bằng chứng hoặc quy trình reviewer nào được Huy duyệt để xác nhận không bất khả kháng, không lỗi khách và source history đã cấp coins/voucher/chưa cấp/không rõ? Nếu chưa có, vòng đầu có thể chỉ review/no-grant bằng dữ liệu release hay cần bổ sung xác minh để demo positive ledger? Không tự bật grant trên tất cả order carrier/platform fault, không tự biến unknown thành có/không FM.
3. **Phạm vi voucher nội bộ còn thiếu:** Demo chỉ cần ghi issuance10.000 + once/kind/receipt, hay phải thể hiện cả expiry/min-spend/redemption lifecycle? Nếu phải thể hiện, Huy cần chốt giá trị/rule tương ứng. Đây là câu hỏi scope còn lại, không hỏi lại eligibility hoặc voucher+coins đã xác nhận.

Đây là câu hỏi cần controller đưa trực tiếp cho Huy, báo cáo không tự trả lời. Các phần source/read model/clock interface draft và bàn giao owner có thể tiếp tục chuẩn bị trong phạm vi đã được phép, nhưng không thực thi nhánh phụ thuộc câu trả lời.

## 5. Phụ thuộc implementation theo chủ sở hữu

| Chủ sở hữu | Việc trước demo | Bàn giao/chờ |
| --- | --- | --- |
| Huy | Spec/plan đã được worker khác chuyển vào .scratch trong lúc review; hoàn thiện extension voucher; sửa clock/failure/publication seams sau quyết định; replay read-only/A3/state/gate; cancellation/return signal; executor policy và receipts | Huy chỉ sửa platform trừ UI, contracts, root config/docs và acceptance_truc. Cần rule A1 thật + auth/origin transport từ Trúc; cần Huy duyệt FM/history/voucher trước release issuance. |
| An Nguyen | Giữ thuật toán A2 hiện có; xác nhận projection/evidence/dependency seam và metadata ngày tạo/bàn giao; thống nhất batch failure/per-order outcomes nếu cần | Request owner sửa logistics_an_nguyen, không để Huy fork lại thuật toán hoặc đổi A2 tests. Progress/QuestionStore vẫn do Huy transaction/state; `progress.py:13`, `questions.py:14–17`. |
| Trúc | API/auth/UI thật, đọc committed view; text session/intent/rules/validator; handoff, cancel second turn/recovery; gate trước proactive và trusted provenance; sau đó web voice | Chờ DTO/gate read view và error semantics Huy; dùng serializer A2. Không lấy mock UI state làm API hoặc client source làm authority. |
| Kiểm chứng chéo | An kiểm platform/A3 ở acceptance_huy; Trúc kiểm A2 ở acceptance_an_nguyen; Huy kiểm A1 thật ở acceptance_truc | Theo `AGENTS.md:5–10` và `docs/team_plan.md:134–142`; mỗi owner sửa implementation của mình, không nới test owner khác. |

Draft chín task là danh sách nền để tái sắp, không phải lý do trì hoãn mọi vertical slice đến cuối. Gắn D0/D1 ngay sau foundation tick/read seam và Trúc text seam; làm D2/D3 khi đủ nền; D4 phụ thuộc policy rõ. Không thêm framework/dependency chỉ vì PR nghiên cứu nêu tên LangGraph/Temporal.

## 6. Evidence và giới hạn lần review này

Đã đọc AGENTS workspace/repo cùng cập nhật demo-first và decision log mới, using-superpowers và Codex adaptation; skill có subagent-stop nên không mở workflow triển khai hoặc spawn child. Đã đọc nghiên cứu orchestration, spec, trạng thái và phần foundation/hand-off của plan đang draft, source A2/platform/A1/UI và contracts liên quan. Không đánh giá thiếu sót chỉ vì tail draft còn đang viết. Không sửa các tài liệu đó. Spec được worker di chuyển thêm banner hai dòng trong lúc review; references spec ở báo cáo đã tăng hai dòng tương ứng.

Không chạy test/benchmark/server và không mở hay đổi DB; vì vậy đây là static review, không phải verification receipt. Chỉ file báo cáo này được tạo. Không gửi yêu cầu tới thành viên khác và không thực hiện Git mutation.

## 7. Cập nhật sau review — các lựa chọn đã được Huy chốt

Ghi chú này thay trạng thái câu hỏi lịch sử ở mục 4; giữ nguyên phần trên như review **trước khi sửa spec**, không coi các lựa chọn đó còn chờ user phê duyệt. Nguồn hiện hành là [quyết định demo Huy](2026-10-31-huy-demo-decisions.md).

- NEXT tiến simulation đúng +30 phút mỗi tick; chat xử lý ngay tại simulation time hiện tại. Host wall time chỉ phục vụ audit, không tiến replay hoặc quyết định freshness.
- Demo cấp quyền lợi trong SQLite runtime nội bộ. Voucher10.000 và coins cùng eligibility đã xác nhận, cấp riêng và once/kind/order; không có ví/coupon/provider Shopee thật. Redemption/expiry ngoài scope; không tự đặt TTL/minimum spend.
- Huy hoặc nhân viên có thẩm quyền có thể xác minh bằng chứng fault/force-majeure từng order và ghi quyết định runtime có audit. Không bỏ qua eligibility, authority, provenance, freshness, amount hoặc idempotency, không sửa DB nguồn.
- Lịch sử cần mapping kỹ thuật riêng theo kind: voucher đã nhận diện không tiêu lượt coins; unknown kind cần giải quyết mapping, không gộp quyền lợi hoặc hỏi lại quyết định đã trả lời.

Theo cập nhật controller, sửa spec và clean-context review đang được thực hiện. Các phát hiện về failure incident/control bền, publication, timestamp chat và owner seams vẫn là yêu cầu cần đối chiếu ở bản sửa; ghi chú này **không xác nhận chúng đã triển khai hay verified**. Không phát sinh câu hỏi user mới từ các lựa chọn đã được chốt ở trên.
