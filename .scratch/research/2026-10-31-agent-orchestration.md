# Điều phối A3, A2 và A1 trong hackathon

Ngày nghiên cứu: 31/10/2026. Phạm vi: kiến trúc chạy agent, không triển khai code hoặc chọn thêm dependency.

## Kết luận

**Giữ thứ tự A3 → A2 → A1 trong mỗi tick. Dùng bộ điều phối Python thuộc platform, chưa thêm agent LLM điều phối.** Sau khi luồng cơ bản chạy đúng, có thể xử lý đồng thời các đơn độc lập trong A2 và các phiên độc lập trong A1. Không cho tin nhắn khách đang chờ bị treo đến tick 30 phút tiếp theo.

Đây là khuyến nghị cho repo hiện tại, không phải kết luận rằng mọi hệ thống nhiều agent đều phải tuần tự. Kế hoạch nhóm đã quy định thứ tự và một cổng thực thi hành động có kiểm quyền. Tài liệu cũng xác nhận chưa có agent hoặc executor chạy thật. [Kế hoạch nhóm](../../docs/team_plan.md) và [quyết định D1–D5](../../docs/decisions.md) là nguồn yêu cầu nội bộ, không phải bằng chứng hiệu năng.

**Quy ước:** “Nguồn xác nhận” mô tả điều tài liệu chính thức nói. “Đề xuất” là suy luận áp dụng vào dự án, chưa phải quyết định mới của nhóm.

## 1. Orchestration không nhất thiết là một LLM

Nguồn xác nhận: Anthropic phân biệt workflow có đường chạy do code định trước với agent để LLM tự quyết các bước. Orchestrator-workers của họ phù hợp khi cần phát hiện và chia việc động, thay vì biết trước toàn bộ việc phải làm. [Anthropic, Building effective agents](https://www.anthropic.com/research/building-effective-agents).

Đề xuất: gọi A3 trước A2 là một quy tắc đã biết. Một hàm Python có thể thực hiện quy tắc đó mà không cần hỏi mô hình “nên gọi ai tiếp theo”. Tên A1/A2/A3 mô tả trách nhiệm, không bắt buộc mỗi thành phần phải là một vòng lặp LLM tự trị.

Bộ điều phối nên quản lý tick, đầu vào, kết quả, timeout, retry và nơi lưu trạng thái. A3 chịu trách nhiệm sức khỏe nguồn; A2 chịu trách nhiệm đánh giá đơn; A1 chịu trách nhiệm hội thoại. Bộ điều phối không tự tạo thêm kết luận logistics, lời hứa giao hàng hoặc số tiền. Đây là ranh giới đề xuất dựa trên [trách nhiệm platform](../../platform_huy/README.md) và [trách nhiệm A1](../../care_truc/README.md).

## 2. Phụ thuộc bắt buộc và phần có thể đồng thời

Trong một tick:

```text
Mốc replay T và dữ liệu as-of T
               |
          A3 kiểm nguồn
               |
       A2 đánh giá các đơn
               |
      A1 chuẩn bị chăm sóc
               |
        Platform / outbox
```

Đây là phụ thuộc dữ liệu. A2 cần biết nguồn nào đáng tin. A1 cần đánh giá A2 tương ứng và giới hạn A3. Chạy cả ba ngay từ đầu có thể khiến A1 dùng đánh giá cũ trước khi biết nguồn đang lỗi. Thứ tự này đã được chốt trong [team plan, mục 1.2](../../docs/team_plan.md).

Nguồn xác nhận: runtime LangGraph chạy các actor được chọn đồng thời trong một bước, nhưng cập nhật channel của bước đó chỉ có hiệu lực ở bước kế tiếp. Có framework graph không làm biến mất phụ thuộc giữa các bước. [LangGraph runtime](https://docs.langchain.com/oss/python/langgraph/pregel).

Đề xuất cho giai đoạn đầu:

| Công việc | Cách chạy | Điều kiện |
| --- | --- | --- |
| A3, A2, A1 của một tick | Tuần tự theo giai đoạn | Cùng mốc dữ liệu, kết quả có định danh |
| A2 đánh giá các đơn | Ban đầu tuần tự; sau đó đồng thời có giới hạn | Không sửa chung đối tượng hoặc ghi chung state từ worker |
| A1 phục vụ các phiên khác nhau | Có thể đồng thời | Tách trạng thái mỗi phiên, kiểm guard trước liên hệ chủ động |
| Nhiều lượt trong một phiên | Theo thứ tự | Không để hai lượt cùng xác nhận hoặc đổi trạng thái hủy |
| Các yêu cầu tiền cho cùng đơn | Qua executor và transaction | Kiểm quyền, một lần mỗi đơn, idempotency |

Giữ rào chắn giữa ba giai đoạn ở bản đầu: A3 hoàn tất, A2 hoàn tất và công bố kết quả, rồi A1 chạy. Chuyển thành pipeline theo từng đơn là một thay đổi kiến trúc riêng cần nhóm thống nhất, không tự diễn giải lại quy tắc A3 → A2 → A1.

Nếu dùng Python async cho các công việc I/O độc lập, `TaskGroup` có từ Python 3.11. Khi một task lỗi ngoài cancellation, các task còn lại trong nhóm sẽ bị hủy; vì vậy cần chọn rõ lỗi một đơn có làm hỏng cả batch hay không. [Python 3.11, Task groups](https://docs.python.org/3.11/library/asyncio-task.html#task-groups). Đề xuất: trả kết quả lỗi có cấu trúc cho lỗi cục bộ dự kiến, nhưng không nuốt lỗi hệ thống hoặc cancellation.

## 3. Tách nhịp đánh giá khỏi hội thoại đang diễn ra

Quy tắc tick 30 phút không nói khách phải đợi 30 phút cho mỗi câu trả lời. Các API chat/voice và ContactTask được mô tả riêng trong [team plan, mục 2](../../docs/team_plan.md). Thiết kế dưới đây là đề xuất tích hợp, cần Huy và Trúc chốt interface.

```text
Tick replay → A3 → A2 → A1 lập việc chủ động
                         |
                 kết quả đã công bố
                         |
Tin nhắn khách → A1 xử lý lượt → phản hồi / yêu cầu hành động
```

Nhánh hội thoại đọc assessment đã hoàn tất có mốc không vượt thời gian nghiệp vụ hiện tại. Nó không phải chạy lại cả batch đơn hàng cho mỗi tin nhắn. Nếu assessment quá cũ hoặc thiếu bằng chứng, A1 trả lời giới hạn thông tin hoặc chuyển nhân viên; không âm thầm lấy tương lai hay bịa ETA.

Nên ghi định danh phiên, thứ tự lượt và assessment được dùng. Trong cùng phiên, xử lý lượt theo thứ tự; trên các phiên khác nhau, có thể đồng thời. Cơ chế lưu message, chống nhận lặp và phiên bản assessment chưa được triển khai sẵn. Đây là phần Huy/Trúc cần thiết kế thêm, không phải khả năng đã có nhờ dataclass.

## 4. A3 chặn liên hệ chủ động, không đóng mọi luồng

Yêu cầu hiện tại: feed `stale/corrupt/missing`, heartbeat A3 thiếu hoặc quá 60 phút phải chặn liên hệ chủ động. Feed stale xét timestamp nguồn quá 30 phút; thời điểm kiểm tra không được biến dữ liệu cũ thành mới. A3 chỉ siết control, không tự nới khi feed hồi phục. [D3](../../docs/decisions.md).

Đề xuất: khi A3 lỗi hoặc timeout, ghi nhận incident và trạng thái không xác định, chặn chủ động. Vẫn có thể lưu đánh giá suy giảm an toàn, tiếp nhận khách, ghi yêu cầu gặp người và chuyển nhân viên. Không diễn giải fail-closed thành việc tắt toàn bộ A1 hoặc giấu sự cố.

Gate phải được kiểm tra lần nữa ngay trước gửi, không chỉ khi xếp hàng. Một tin được chuẩn bị lúc nguồn còn tốt có thể đến lượt gửi sau khi control đã bị siết. Cần tuần tự hóa quyết định cấp quyền gửi với cập nhật control ở platform; không giữ transaction SQLite mở trong lúc gọi mạng. Nếu control đổi sau khi provider đã nhận tin, không thể giả định thu hồi được tin đó. Team cần xác định rõ thời điểm hệ thống coi việc gửi đã được cho phép.

## 5. Snapshot, thời gian và chống đọc trước

DB nguồn bất biến, mở read-only. Mỗi tick dùng cùng cutoff; scan chỉ được thấy khi `ingested_at <= T`. `event_at` sắp tiến trình đã nhìn thấy, không thay cursor. Các bản ghi cùng timestamp phải xử lý hết trước checkpoint. [D5](../../docs/decisions.md).

Đề xuất mang một context chung gồm `run_id`, cutoff và phiên bản kết quả nội bộ. A1 không đọc một phần assessment của tick mới cùng phần còn lại của tick cũ. Công bố kết quả hoàn tất theo đơn hoặc batch phải có chính sách rõ; bản đầu nên công bố cả batch sau khi A2 hoàn tất.

Phân biệt hai đồng hồ: timestamp nghiệp vụ quyết định quyền thấy dữ liệu và luật thời gian; đồng hồ đơn điệu của runtime đo timeout gọi mạng. Không dùng thời gian máy hiện tại để kết luận đơn replay đã trễ. Phiên bản context, kho assessment và cơ chế công bố là đề xuất bổ sung, không phải trường contract hiện có.

## 6. Retry, checkpoint và tiền

Nguồn xác nhận: LangGraph có checkpointer cho trạng thái theo thread; lưu RAM không sống qua restart. Khi dùng interrupt, node chứa interrupt được chạy lại từ đầu khi tiếp tục. Side effect vì vậy vẫn cần idempotency. [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).

Nguồn xác nhận: transactional outbox ghi thay đổi nghiệp vụ và bản ghi thông báo trong cùng transaction để tránh dual write không nhất quán. Bộ chuyển tiếp vẫn có thể gửi trùng, nên bên nhận cần xử lý idempotent. Outbox không tự đảm bảo mỗi tác động bên ngoài chỉ xảy ra đúng một lần. [AWS, Transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html).

Đề xuất checkpoint của một bước chỉ tiến khi output bắt buộc đã lưu bền. Nếu crash sau khi lưu nhưng trước khi checkpoint, chạy lại phải nhận ra kết quả cũ. ID/key ổn định cho cùng thao tác, không tạo key ngẫu nhiên mới mỗi retry. Hết hạn claim cần có chính sách phục hồi để action không nằm `claimed` vĩnh viễn.

SQLite chỉ có một write transaction đồng thời, dù có nhiều reader. [SQLite Transactions](https://www.sqlite.org/lang_transaction.html). Vì vậy nên để worker trả dữ liệu cho một nơi ghi state với transaction ngắn; không giữ khóa DB trong thời gian chờ LLM, xác nhận khách hoặc nhân viên.

Các ràng buộc tiền thuộc [D4](../../docs/decisions.md): A1 tạo yêu cầu; `execute_action` kiểm nguồn, số tiền tính bằng luật, bằng chứng, approval và idempotency. Chỉ xét xu khi khách yêu cầu text trong chat do A1 mở, đơn trễ ít nhất hai ngày, không lỗi khách/bất khả kháng, một lần mỗi đơn. Voice không cấp xu. Xác nhận hủy phải gắn đúng yêu cầu và đơn; câu “đồng ý” không tự đủ để thực thi.

Các bảng hiện tại chưa tạo thành workflow engine hoàn chỉnh. Kho assessment, checkpoint các bước tick, lưu từng message/xác nhận hủy và lease/attempt policy là các interface hoặc phần lưu trữ cần Huy thiết kế thêm. Không sửa schema trong nghiên cứu này. Nguồn hiện trạng: [schema state](../../contracts/schema_state.sql), [team plan, mục 2.2](../../docs/team_plan.md).

## 7. Mẫu bộ điều phối tối thiểu

Pseudocode đề xuất, không phải API đang tồn tại. Các tên thao tác lưu trạng thái là yêu cầu thiết kế:

```text
run_tick(T):
  context = freeze_asof_context(T)
  guard = run_A3_or_record_failure(context)
  if guard.completed_successfully:
    persist_actual_A3_heartbeat_health_and_tightened_controls(guard)
  else:
    persist_incident_and_block_proactive_contact(guard.failure)
    # Do not fabricate a successful heartbeat on failure.

  assessments = run_A2_with_degraded_results_if_needed(context, guard)
  publish_completed_assessments(assessments)

  requests = run_A1_proactive_planning(context, assessments, guard)
  persist_requests_and_step_checkpoint_atomically(requests)

dispatch(request):
  if not valid_current_permissions_and_required_facts(request):
    mark_blocked(request)
    return
  if proactive_contact(request) and not latest_A3_gate_allows(request):
    mark_blocked(request)
    return
  if requires_approval(request) and not has_valid_approval(request):
    persist_waiting_for_approval(request)
    return
  if financial(request):
    execute_action_with_business_rules_and_deduplication(request)
  else:
    send_with_stable_key_and_record_result(request)

on_customer_message(message):
  serialize_this_session_only()
  load_completed_asof_assessment_and_session()
  apply_rules_then_optional_LLM_then_response_validator()
  persist_turn_and_proposed_actions()
```

Không `return` ngay khi A3 lỗi rồi bỏ mất incident hoặc output suy giảm. Không để `needs_approval` hoặc `source` do client gửi trở thành quyền thực thi. Source thực phải đến từ ngữ cảnh server được tin cậy. [Team plan, mục 2.1](../../docs/team_plan.md).

## 8. Lỗi nào cần xử lý trước demo?

| Tình huống | Hành vi đề xuất |
| --- | --- |
| A3 timeout, mất heartbeat | Ghi sự cố, chặn chủ động; giữ đường nhận khách và handoff |
| A2 lỗi một đơn | Ghi thất bại riêng, không công bố assessment thành công giả |
| LLM chậm hoặc validator từ chối | Dùng mẫu an toàn theo facts hoặc chuyển người |
| Khách xác nhận hủy hai lần | Một yêu cầu có hiệu lực, không tạo hai lần thực thi |
| Provider nhận tin rồi mất phản hồi | Trạng thái chưa chắc chắn; đối soát theo key nếu provider hỗ trợ |
| Crash sau ghi ledger | Retry nhận ra đã thực thi, không cấp lần nữa |
| Nhân viên chưa duyệt | Giữ trạng thái chờ, không khóa toàn tick hoặc transaction |

Nguồn xác nhận: Temporal mô tả retry policy là cấu hình thời điểm và cách thử lại; Activity bị lỗi mặc định được retry, còn Workflow Execution không có retry policy mặc định. [Temporal Retry Policies](https://docs.temporal.io/encyclopedia/retry-policies). Đề xuất cho repo: phân biệt lỗi tạm thời có thể retry với vi phạm nghiệp vụ không nên retry. Chưa chọn số lần/thời hạn retry khi chưa có yêu cầu provider và thời lượng demo.

## 9. Khi nào nâng cấp?

| Lựa chọn | Phù hợp lúc nào | Đánh giá cho hiện tại |
| --- | --- | --- |
| Python điều phối + state SQLite | Luồng cố định, phạm vi hackathon | Khuyến nghị đầu tiên |
| LangGraph với checkpointer bền | Nhiều nhánh hội thoại, pause/resume, cần quan sát graph | Cân nhắc khi nhu cầu này rõ |
| Temporal | Workflow dài, nhiều worker, phục hồi/retry vận hành | Chưa có bằng chứng dự án cần ngay |
| LLM orchestrator | Cần khám phá tác vụ chưa biết trước | Có thể thử cho điều tra sự cố dạng đề xuất |

LLM điều tra sự cố trong tương lai có thể đề xuất truy vấn và tổng hợp bằng chứng, nhưng không được bỏ gate A3 hoặc tự cấp quyền tiền. Đây là hướng nghiên cứu tiếp, chưa phải quyết định triển khai. Bài Anthropic có nguồn gốc tháng 12/2024 và hiện tự cảnh báo tooling đã thay đổi; nghiên cứu chỉ dùng phân biệt kiến trúc của bài, không dùng danh sách công cụ cũ để chọn stack. [Anthropic](https://www.anthropic.com/research/building-effective-agents).

## 10. Những điểm team cần chốt

1. Huy lưu assessment hoàn tất, checkpoint và phiên bản context ở đâu?
2. Trúc nhận guard/context qua interface nào; lỗi guard sẽ trả trạng thái gì?
3. Lưu từng message, pending cancellation và chống lặp xác nhận thế nào?
4. Provider chat/voice có hỗ trợ idempotency hoặc tra cứu kết quả gửi không?
5. Chính sách xử lý tick lỗi một phần, claim bỏ dở và yêu cầu quá hạn là gì?

Giới hạn: chưa benchmark latency/throughput, chưa thử framework hoặc end-to-end. Không kết luận Python nhanh hơn một framework theo số đo. Đây là nghiên cứu tài liệu và đối chiếu quy tắc repo. Các câu hỏi trên cần được chuyển thành spec/interface trước khi ghép runtime; không có thay đổi hợp đồng hay dependency trong file này.
