# Nghiên cứu cổng thực thi của Huy — 2026-10-31

Phạm vi: đặc tả để review và lập kế hoạch, chưa triển khai. Chỉ Huy sở hữu contracts, state và Python service thực thi; Trúc sở hữu HTTP/auth/UI/A1, An Nguyen sở hữu A2. Không thêm route, không chọn framework/provider, không viết vào DB nguồn. Baseline do controller cung cấp: `huy`, HEAD `41cf049`; báo cáo này không chạy Git hay kiểm thử.

Steering mới nhất: Huy đã duyệt scope coins + cancel; công thức coins vẫn 5%, floor nghìn, min 10.000/max 1.000.000. Voucher/refund là hướng tương lai, tiếp tục `policy_not_configured`. Huy đã chọn “Hiển thị số lần hoàn trả có bằng chứng, shop tự đánh giá”; phần bổ sung 10 ghi giới hạn dữ liệu và seam đọc, không có cảnh báo fraud tự động/ngưỡng/model.

## 1. Hợp đồng đã có và khoảng trống thực tế

Đã đọc `AGENTS.md` cấp workspace và repository, `docs/team_plan.md`, `docs/decisions.md`, `contracts/{types.py,params.py,schema_state.sql,__init__.py}`, `platform_huy/README.md`, `care_truc/README.md`, A2 `models.py/service.py/assessment.py`, `docs/data_audit.md` và tests schema hiện tại. Đọc metadata DB release bằng URI `mode=ro`; không truy vấn dữ liệu cá nhân và không mở truth/heldout. Đã đọc Superpowers using-superpowers và Codex adaptation; bản skill có ngoại lệ cho subagent được giao tác vụ cụ thể.

`Action` hiện có đúng các trường `action_id`, `order_id`, `kind`, `amount_vnd: int`, `source`, `requested_at`, `idempotency_key`, `evidence_ref: str`, `needs_approval: bool`, `queue: str`, `confirmation_id: str | None = None`. Không có actor/contact/message/assessment ID. Đây là request, không phải authority. Không đổi constructor hiện có để bắt buộc thêm trường làm vỡ caller/test cũ.

| Kind | Source hợp lệ hiện tại |
| --- | --- |
| coins | a1 |
| cancel_request | a1, app |
| eta_notice | a1 |
| voucher | rule |
| refund, shipping_fee_refund | cancel_reviewer |

`ALLOWED_SOURCES` không có `a2`, `a3`, `llm`. Type hints không kiểm runtime và SQL chỉ kiểm cặp chuỗi được khai báo, không chứng minh ai gửi request. `Action(source='cancel_reviewer')` tự nó không cấp quyền review.

`late_xu_for` đã là hàm pure đúng công thức integer: `(items_value_vnd * 5 // 100_000) * 1_000`, clamp 10.000–1.000.000; None/0 trả 10.000; từ chối bool/float/âm. Không sửa công thức hoặc coi quote là eligibility. Tên `amount_vnd` trong Action được giữ tương thích; đối với coins, số đó là số xu theo D4, ledger dùng `amount_xu`. Chưa có tỷ giá hay quyền đổi xu thành tiền.

`schema_state.sql` có 8 bảng: `contact_log`, `outbox`, `ledger_new`, `guard_heartbeat`, `feed_health`, `incidents`, `supervisor_questions`, `controls`. Outbox có UNIQUE key, CHECK kind/source, status pending/claimed/succeeded/failed/blocked. Ledger xu có UNIQUE order/key/action, FK outbox/contact và range/rounding amount. Schema chưa chứng minh contact thuộc cùng order với action, A1 thật sự mở chat, customer thật sự xin xu, source được xác thực, amount đúng công thức, review hợp lệ hay ledger lịch sử đã kiểm. Không có executor hiện tại.

A2 cung cấp `OrderAssessment` với `late_days`, `fault_party`, reasons/evidence; `evaluate_tick(...)` và `assessment_payload(...)` là Python interface đã có. Comment trong serializer nói Huy routes nhưng ownership hiện tại giao HTTP cho Trúc. `OrderFacts` không có items value, customer identity, compensation history hoặc confirmation. Không lấy chúng từ text/LLM. A2 dùng số ngày lịch VN: `max(0, date_VN(delivered_at or tick_at) - guaranteed_date)`. Ví dụ guaranteed_date 29/10, tick 31/10 00:00 VN cho late_days=2; đây không phải 48 giờ sau 29/10 23:59:59. Cần kế hoạch giữ đúng semantics A2 hoặc đưa Huy quyết định nếu muốn đổi, không lặng lẽ sửa ngưỡng.

Metadata nguồn xác nhận `orders.items_value_vnd`, `shipping_fee_vnd`, `payment_method`, `guaranteed_date`, `created_at`, `cancelled_at`; không thấy bảng payments. `compensation_ledger` có `entry_id/order_id/kind/amount_vnd/actor/reason_text/created_at/idempotency_key/source_ref`, không có ingested_at. `external_events` có ts/kind/province/title/detail, không có force_majeure cho từng order. Theo audit có voucher/refund/shipping_fee_refund lịch sử, chưa có coins; 1.115 ledger rows ngoài lát orders. Đây là số audit đã ghi, không phải thống kê đo lại trong nghiên cứu này.

## 2. Nguồn tham khảo và hàm ý thiết kế

SQLite cho nhiều reader nhưng chỉ một writer; `BEGIN IMMEDIATE` lấy write transaction sớm và có thể trả SQLITE_BUSY. Đề xuất transaction ngắn, retry contention có giới hạn, không gọi provider/network trong transaction. Đây là lựa chọn áp dụng cho repo, không phải yêu cầu nghiệp vụ. [SQLite transactions](https://www.sqlite.org/lang_transaction.html).

UNIQUE coi các NULL là khác nhau; key chống trùng phải NOT NULL. CHECK không thay runtime authorization, và affinity không bảo đảm kiểu integer; tiếp tục dùng type validation Python cùng `typeof`/CHECK cho tiền. `CREATE TABLE IF NOT EXISTS` không cập nhật bảng cũ, nên cần migration version rõ ràng khi đổi schema. [SQLite CREATE TABLE](https://www.sqlite.org/lang_createtable.html).

AWS mô tả ghi business state và outbox cùng transaction, chỉ phát dữ liệu đã commit; dispatcher vẫn có thể gửi trùng nên consumer phải idempotent. Đây là cơ sở cho phân biệt ledger commit với delivery; không suy từ outbox ra bảo đảm tiền ở provider ngoài hệ thống chỉ chạy một lần. [AWS transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html).

Stripe API v1 lưu kết quả sau khi execution bắt đầu, so sánh payload cho key cũ; key có thể được xóa sau ít nhất 24 giờ. Dùng đây làm mẫu kiểm cùng key/cùng payload và cảnh báo thời hạn provider, không chọn Stripe hay áp thời hạn 24 giờ cho state của dự án. [Stripe idempotent requests](https://docs.stripe.com/api/idempotent_requests).

## 3. Các phương án

| Phương án | Ưu điểm | Nhược điểm / kết luận |
| --- | --- | --- |
| Chỉ ghi thẳng ledger sau kiểm Python | Ít code | Không lưu đầy đủ quyết định/retry/delivery; khó audit; không chọn |
| Một SQLite runtime DB, cổng Python, receipt + ledger + outbox atomically | Phù hợp scaffold, không cần dependency mới, kiểm chứng concurrency/crash được | Cần migration và evidence provenance; chọn cho bản đầu |
| Queue/provider và saga từ đầu | Có hướng tích hợp tiền thật | Chưa có amount policy/provider/transport; không cần cho scope này |

Khuyến nghị: coins chỉ là hiệu ứng ledger runtime trong bản đầu; `execute_action` là cổng duy nhất ghi financial effect. Outbox action mô tả request/kết quả, delivery riêng mô tả thông báo hoặc tác vụ provider tương lai. Không thông báo đã trả tiền ngoài hệ thống khi mới ghi ledger. Voucher/refund/shipping refund trả `policy_not_configured`, không gọi transport, không ghi vào ledger xu.

## 4. Authority, provenance và eligibility

Trúc xác thực HTTP user và ownership; Huy vẫn yêu cầu server-resolved principal/capability khi gọi service. `ExecutionContext` do trusted server wiring tạo, không deserialize từ JSON. Mapping source được bind vào service entry point cho A1/app/rule/reviewer; so `Action.source` với source đã bind. Actor và role lấy từ authenticated session, không từ Action/evidence/customer text. Python cùng process không có sandbox bảo vệ khỏi code cố tình gian lận; ranh giới này bảo vệ request bên ngoài và caller integration, không hứa chống malicious module được quyền ghi DB.

`evidence_ref` phải resolve tới record immutable được server lưu, không parse một chuỗi như `contact_log:...` rồi coi đó là chứng minh đủ điều kiện. Receipt lưu resolved actor/source/order/contact/message/assessment/policy version và hash evidence snapshot. Chuỗi legacy có thể đọc để hiển thị; không tự tạo message hoặc chứng nhận từ nó. Evidence record minted bởi adapter/A1 runtime; source text không được tạo role, request signal hay FM fact. Reviewer không được tự nhập số tiền để vượt cổng.

Coins cần tất cả điều kiện sau trong cùng quyết định thực thi:

1. Đơn tồn tại và visible as-of; actor được quyền với đơn; principal là A1 server, không app/A2/A3/LLM.
2. Evidence trỏ đúng order, contact đã opened, channel=chat, initiated_by=A1; authenticated customer của đơn có message text xin bù xu rõ ràng trong phiên. Transcript voice, historical ticket, pasted assistant text, app mở chat không đủ. Dùng customer message ID gốc, origin text/voice được server cố định; không dựa riêng vào content có chữ xin xu.
3. Assessment do server lưu/resolve thuộc đúng order, không ở tương lai, evidence đã visible. late_days >=2 theo A2/D1; known structured fault không phải customer hoặc force_majeure. Unknown/mâu thuẫn/thiếu bằng chứng phải trả blocked/review với mã riêng, không coi unknown là đã chứng minh không có lỗi khách/FM. Cách phân loại absence FM cần Huy chốt rõ trước bật cấp tiền hàng loạt.
4. A3 chỉ siết: control disable-compensation nếu được định nghĩa có thể chặn, không tự cấp tiền/miễn bước. Stale feed không dùng để chứng minh financial facts. Quy tắc heartbeat hiện tại chặn proactive contact; không tự mở rộng thành cấm mọi inbound/review/cancellation nếu chưa có quyết định. Guard được kiểm ngay trước gửi proactive notice/contact qua service tương ứng.
5. `amount_vnd` bằng quote từ orders.items_value_vnd đã đọc server-side; type int chính xác, không bool; amount khác quote bị từ chối thay vì tin LLM. Negative/malformed items value bị từ chối; chỉ None/0 áp fallback đã chốt.
6. Không ledger xu mới của order; kiểm source ledger bằng order và timestamp visible, không join orders trước làm mất lịch sử. Không dùng những dòng tương lai ở replay để chặn. Check key lịch sử nhằm phát hiện collision, không để key mới né once/order. Loại lịch sử nào tiêu thụ quyền xu cần được chốt ở mục 8.

Không ép status='late' duy nhất làm eligibility: status có ưu tiên exception/unknown_feed/customer_fault; cần đánh giá facts và gate rõ ràng. Exception không tự được xu hoặc tự bị loại theo một chính sách chưa duyệt. Unknown_feed/contradiction không chứng minh điều kiện tài chính.

## 5. State bổ sung có thể migration mà giữ test cũ

Giữ nguyên các bảng và constructor v0. Dùng additive companion tables, không thêm trigger bắt mọi INSERT outbox/ledger cũ phải có evidence mới: acceptance_huy đang cố ý insert fixture v0 trực tiếp. Production service áp invariant bổ sung; constraint cũ vẫn nguyên. Không sửa tests của An Nguyen để đổi kỳ vọng. Migration bằng `schema_migrations(version PRIMARY KEY, applied_at)` trên state, áp transactional DDL khi có thể; không chạy `executescript` tùy tiện giữa transaction business của Python.

| Bảng đề xuất | Cột/constraint cốt lõi |
| --- | --- |
| `customer_messages` | `message_id TEXT PRIMARY KEY NOT NULL`, `contact_id` FK contact_log, `order_id`, `customer_id`, `origin CHECK IN ('text','voice_transcript')`, `created_at`, `body`, `request_code NULL hoặc 'late_compensation'`, `recorded_by`; immutable qua service |
| `execution_evidence` | `evidence_id PRIMARY KEY NOT NULL`, `order_id`, `contact_id/message_id` FK nullable, `assessment_at`, `visible_at`, `policy_version`, `payload_json CHECK json_valid`, `sha256 NOT NULL`, `created_by`; giữ snapshot as-of và provenance |
| `action_receipts` | `action_id PRIMARY KEY REFERENCES outbox`, `request_hash`, `actor_id`, `attested_source`, `evidence_id` FK, `decision_code`, `result_json`, `decided_at`; key nằm outbox UNIQUE; receipt/result committed cùng effect |
| `cancel_reviews` | `cancel_id PRIMARY KEY NOT NULL`, `request_action_id UNIQUE` FK outbox, `order_id`, `customer_id`, `status` enum, `requested_at`, `challenge_hash`, `challenge_issued_at`, `confirmed_at`, `confirmation_id UNIQUE` nullable, `reviewed_at/by`, `review_reason`, `version INTEGER`; hash challenge không lưu raw secret |
| `delivery_outbox` | `delivery_id PRIMARY KEY NOT NULL`, `action_id` FK, `purpose`, `provider_key UNIQUE NOT NULL`, `payload_json`, `status CHECK IN ('pending','claimed','succeeded','failed','unknown')`, `attempt_count`, `lease_until`, `claim_token`, `next_attempt_at`, `provider_reference`, `last_error`, UNIQUE(action_id,purpose) |
| `financial_effects` | Dự phòng non-coins: `effect_id PRIMARY KEY`, `action_id UNIQUE` FK, `order_id`, `kind CHECK IN ('voucher','refund','shipping_fee_refund')`, `amount_vnd` integer positive, `policy_version`, `review_id`, `provider_reference`, `created_at`; không tạo effect cho kind bị policy_not_configured |

Chưa bắt buộc tạo financial_effects trong unit đầu khi mọi non-coins đều disabled; phải có migration riêng trước bật. Không dùng UNIQUE(order_id) chung cho các khoản refund/voucher chưa có quy tắc tương thích. Khi review/refund được bật phải có unique business key và cap tổng refund theo payment/order; chưa có payment evidence nên chưa xác định được cap đúng.

FK bật trên mỗi connection, không chỉ lần apply schema. Trong transaction kiểm quan hệ `message.order_id == contact.order_id == evidence.order_id == action.order_id`; contact của ledger cũng phải khớp. Không đánh giá hash như chữ ký bảo đảm authority: authority đến từ writer được bind, hash chỉ nhận diện snapshot/payload.

## 6. Transaction, retry và bảo đảm chính xác

Luồng coins đề xuất:

```text
Validate shape and resolve trusted principal/evidence/source snapshot
BEGIN IMMEDIATE
  Lookup outbox by idempotency key
  If found: compare canonical request hash + actor/source binding
    same -> return persisted result; different -> idempotency_conflict
  Recheck current controls, evidence bindings and historical/local eligibility
  Insert outbox action with server-derived queue/approval policy
  If rejected: insert receipt, mark blocked, COMMIT, return stored denial
  Insert ledger_new (UNIQUE order/key/action)
  Insert receipt with immutable result
  Insert delivery_outbox only for configured post-commit notification
  Set outbox succeeded (local ledger effect committed)
COMMIT
Return stored result
```

Canonical hash gồm order/kind/amount/evidence_ref/confirmation và principal/source; queue/approval được server quyết định. Không đưa server-generated action ID và thời gian xử lý vào semantic hash. Nếu requested_at do client có giá trị nghiệp vụ cần bind/validate thì contract phải quy định rõ; dùng server clock cho quyết định và không cho requested_at đổi as-of. Cùng key/payload trả đúng action/result đã lưu, kể cả blocked; khi tình huống thay đổi caller tạo request key mới. Khóa key global như schema hiện tại, không scope theo order để vô tình cho dùng cùng key cấp nhiều đơn. Không giữ key chỉ 24 giờ: once/order sống theo ledger, không theo cache TTL.

Không dùng `INSERT OR REPLACE` cho receipt/ledger/outbox. UNIQUE violation không mặc nhiên là retry thành công: đọc lại key/hash/result, phân biệt duplicate_order với key conflict. BEGIN IMMEDIATE serialize check+insert trong runtime DB; SQLITE_BUSY trước commit phải rollback/retry toàn transaction có giới hạn, không báo thành công. Inject failure sau ledger insert nhưng trước receipt/outbox update phải rollback toàn bộ.

DB nguồn bất biến có thể đọc snapshot as-of trước transaction runtime, giữ source identity/as-of/digest trong evidence; current controls/local grants kiểm lại bên trong. Source ledger muốn kiểm phải available và parseable; không đoán ledger rỗng khi query lỗi. Timestamps source dùng offset thật, state UTC canonical; không so string có offset hỗn hợp trực tiếp.

Bảo đảm bản đầu: tối đa một ledger xu committed mỗi order trong một runtime DB, retry cùng key trả cùng kết quả; action/ledger/receipt/delivery record cùng commit hoặc cùng rollback. Điều này không bảo đảm once/order qua việc xóa runs hoặc hai run DB độc lập: demo reset tạo một thế giới runtime mới. Production cần một state authority dùng chung/persistent hoặc đối soát provider, không được tự cho rằng source ledger có các grant mới.

Dispatcher claim atomic bằng conditional UPDATE và token/lease. Sau commit mới gửi provider; ACK chỉ update nếu token còn hợp lệ. Crash sau provider thành công trước ACK có thể gửi lại: dùng cùng provider_key và provider idempotency/status lookup. Nếu provider không hỗ trợ dedup hoặc key hết hạn, trạng thái `unknown` cần reconciliation/human, không tự retry gây trả hai lần. Receipt local succeeded không được hiển thị thành external delivered. Trong phạm vi chưa có transport/provider thật, không gọi mạng hoặc tuyên bố external exactly-once.

## 7. Hủy, review và Python interface bàn giao Trúc

Hủy cần state machine `requested -> awaiting_confirmation -> confirmed -> awaiting_review -> approved/rejected`; có thể gộp confirmed/awaiting_review khi transaction tạo queue. Request đầu không đồng thời coi là lần xác nhận thứ hai. Confirmation là challenge mới, bind order/customer/cancel request và được consume một lần; text “hủy” trong lượt cũ hoặc `confirmation_id` bất kỳ không đủ. Expiry/reconfirm khi order thay đổi là quyết định cần chốt; có thể bảo vệ replay bằng version trước khi chọn thời hạn cụ thể.

`needs_approval=False`, `queue='fast'`, `source='cancel_reviewer'` từ caller không bypass server policy. Request hủy và approval chỉ ghi workflow/runtime; DB nguồn bất biến không nhận UPDATE cancelled_at. Refunding không được tự phát sinh khi confirm/approve hủy. Reviewer có principal/capability riêng, ghi quyết định lý do và optimistic version; retry approve không tạo refund thứ hai. Chưa có rule amount/refund eligibility thì trả policy_not_configured dù reviewer approve.

Interface sketch, chưa phải code đã tồn tại:

```python
@dataclass(frozen=True)
class ExecutionContext:
    principal_id: str
    attested_source: ActionSource
    customer_id: str | None
    capabilities: frozenset[str]
    # Constructed by trusted server wiring, never from request JSON.

@dataclass(frozen=True)
class ExecutionResult:
    action_id: str
    decision: str
    reason_codes: tuple[str, ...]
    amount: int | None
    unit: str | None
    ledger_id: str | None
    delivery_status: str | None
    replayed: bool

def execute_action(action: Action, *, context: ExecutionContext) -> ExecutionResult: ...
def request_cancellation(order_id: str, *, context: ExecutionContext,
                         idempotency_key: str) -> CancellationResult: ...
def confirm_cancellation(cancel_id: str, token: str, *,
                         context: ExecutionContext,
                         idempotency_key: str) -> CancellationResult: ...
def review_cancellation(cancel_id: str, decision: str, *, expected_version: int,
                        reason: str, context: ExecutionContext,
                        idempotency_key: str) -> CancellationResult: ...
def list_review_queue(*, context: ExecutionContext) -> tuple[ReviewItem, ...]: ...
def list_order_actions(order_id: str, *, context: ExecutionContext
                       ) -> tuple[ActionView, ...]: ...
```

Đề xuất source-specific bound factory/service tạo context thay vì cho mọi caller truyền arbitrary attested_source. Các hàm workflow gọi private common gate để persist action; mọi financial mutation đi qua public execute_action. A1 message/evidence recording là service seam riêng phải thống nhất với Trúc; Trúc không tự insert ledger hay mint source role. HTTP adapter map lỗi validation/permission/not-found/conflict/blocked ra status phù hợp theo thống nhất, Huy không viết route. A2 assessment được resolve bởi platform, không nhận JSON assessment từ khách làm authority.

## 8. Những quyết định còn thiếu, không được tự coi đã được duyệt

- Voucher/refund/shipping_fee_refund: điều kiện, amount, currency, cap, COD/prepaid/partial refund, shipping fee payer, review authority và transport chưa được chốt. Giá trị item/shipping fee có sẵn không tự chứng minh số đã thanh toán hoặc quyền hoàn.
- “Một lần mỗi đơn” tiêu thụ bởi coins/late-compensation hay bởi mọi voucher/refund lịch sử? D4 chưa nêu lịch sử kind khác tương đương xu. Cần enum/mapping policy rõ. Trước khi chốt, không tự coi mọi voucher là coin grant hoặc bỏ qua lịch sử; order có historical compensation không rõ mapping trả review. Source coins/late-compensation phù hợp policy phải chặn lần hai kể cả key khác.
- Unknown fault và chứng minh “không bất khả kháng”: structured carrier/platform fault có đủ không, evidence FM cần match thời gian/địa bàn thế nào? Thiếu classifier không được default FM=false. Không thêm ngưỡng confidence tự chọn thành business rule.
- “Hai ngày” hiện là late_days ngày lịch của A2; có cần 48 giờ sau hết ngày không? Nếu đổi, cần contract/test phối hợp An Nguyen.
- Coin request cần active chat tại thời điểm execute hay chấp nhận message hợp lệ sau khi chat completed; TTL message/challenge/review; quyền self-review. Cho đến khi chốt, binder phải xác nhận đã opened và message nằm trong phiên, không tự đặt TTL 24h hay cấm self-review như rule đã duyệt.
- A3 controls key/scope được siết, operator nào được nới; financial freshness khác proactive heartbeat ra sao. Không tự biến lỗi guard thành quyền reviewer hoặc cấm workflow inbound.

## 9. Kịch bản và kết quả mong đợi để chuyển thành test

Đây là test specification chưa thực thi. Fixture tối thiểu trong memory/file tạm không trở thành world data; concurrency dùng hai connections cùng SQLite state file, không hai DB memory độc lập.

| Input / tình huống | Expected result |
| --- | --- |
| A1, chat A1-opened, đúng customer text, late_days=2, known eligible facts, value=239.999 | 11.000 xu, đúng một ledger và receipt; outbox succeeded local |
| value None/0; value 20.154.000 | Quote 10.000; quote cap 1.000.000; eligibility vẫn kiểm riêng |
| value bool/float/âm; Action amount khác quote | validation/amount_mismatch, không ledger |
| source khai a1 nhưng principal app/A2/A3/LLM | permission_denied, không ledger |
| source refund/cancel_reviewer từ customer JSON | permission_denied dù matrix chuỗi hợp lệ |
| voice transcript có câu xin xu; historical ticket; customer-opened chat | invalid_request_provenance, không ledger |
| contact/message thuộc order/customer khác hoặc message ở tương lai | evidence_binding_invalid, không ledger |
| late_days=1; customer fault; force_majeure | ineligible theo reason riêng |
| unknown fault/FM; evidence stale/conflicting/unavailable | blocked/review, không giả định đủ điều kiện |
| cùng key và semantic payload gửi 2 lần | cùng action/result, một ledger; lần hai replayed=true |
| cùng key nhưng đổi order/amount/evidence/principal | idempotency_conflict, không ghi effect mới |
| cùng order hai key, hai connections cạnh tranh | một grant; một duplicate_order hoặc retry đọc kết quả, không 2 ledger |
| failure giữa ledger và receipt/status commit | rollback tất cả, retry chỉ grant một lần |
| source ledger visible đã có grant phù hợp policy; grant tương lai | visible chặn; tương lai không được leak vào quyết định hiện tại |
| history ngoài lát orders | lookup theo order nguồn không mất row; không suy customer từ orphan |
| source ledger lỗi/không đọc được | blocked history_unavailable, không coi lịch sử rỗng |
| cancel_request đầu, caller set needs_approval false | awaiting_confirmation, không hủy/hoàn tiền tự động |
| token sai/chưa phát hành/khác owner/tái dùng hoặc version cũ | reject/conflict; không tạo queue/effect lần hai |
| confirm hợp lệ, reviewer approve nhưng thiếu refund policy | review được lưu; non-coins policy_not_configured, không ledger xu |
| crash sau provider effect trước ACK | retry cùng provider_key nếu provider dedup hợp lệ; nếu không rõ thì unknown/reconcile |
| A3 cố grant tiền hoặc nới control | denied; control tighten không sửa amount/eligibility |

Đánh giá review cần kiểm cả negative path và transaction fault injection, không chỉ test UNIQUE cũ. Giữ nguyên acceptance_huy và acceptance_an_nguyen thuộc owner khác. Huy viết test cross-owner A1 trong acceptance_truc và đề nghị An Nguyen thêm test platform trong acceptance_huy; test riêng implementation của Huy đặt theo conventions thống nhất trong plan. Import/pytest/diff checks chỉ được báo đạt khi controller thực sự chạy ở giai đoạn implementation.

## 10. Bổ sung: lịch sử yêu cầu trả hàng cho shop

Metadata và aggregate được đọc lại bằng SQLite `mode=ro` sau steering; không đọc/xuất tên, điện thoại, địa chỉ. `returns` có `return_id`, `order_id`, `requested_at`, `reason`, `status`, `decided_at`, `refund_vnd`; không có ingested_at/returned_at/status history. Reason enum là damaged/wrong_item/not_as_described/missing_part/changed_mind/not_received/fake; `fake` là reason của yêu cầu về hàng, không chứng minh khách gian lận. Status enum requested/approved/rejected/refunded là trạng thái cuối lưu trong row, không phải chuỗi chuyển trạng thái theo thời gian.

Đo trên toàn release: 522 request; requested_at từ 19/10/2026 19:05:59 đến 09/11/2026 03:27:30 +07:00; 0 thiếu liên kết returns→orders→customers trong bản hiện tại. Đây là coverage của lát release, không phải lịch sử cả đời khách và không phải counts tại tick 31/10. Ngay cả sau cutoff cũng không được hứa có toàn bộ đơn/trả hàng của khách ngoài lát.

Join chuẩn là `returns.order_id -> orders.order_id -> orders.customer_id`; lọc `orders.seller_id` bằng seller principal server trước khi trả payload cho shop. Không join bằng tên, phone hoặc mã order tự trích trong text. Candidate request chỉ visible nếu `requested_at <= as_of` và order `created_at <= as_of`; adapter parse timezone-aware hoặc normalize UTC trước so sánh. Không dùng future request hoặc future order. Không dùng `returns.status='refunded'` hoặc refund_vnd để khẳng định đã hoàn tiền tại requested_at: thiếu timestamp refund riêng nên không chứng minh được transition as-of. Bản đầu chỉ đếm request theo requested_at, ẩn status/refund tương lai; trả `status_history_available=False`.

Đề xuất Python read interface `get_return_history_signal(order_id, *, as_of, context) -> ReturnHistorySignal`, resolve customer/seller từ order bên trong; service của Huy kiểm seller scope, HTTP auth do Trúc thực hiện. Payload mô tả: `signal_code='return_history'`, `visible_request_count`, `visible_order_count_with_requests` (COUNT DISTINCT order, không coi nhiều row là nhiều đơn), `window_start`, `window_end=as_of`, `observed_requested_at_min/max`, `scope='seller_visible_release_slice'`, `coverage_complete=False`, `unknown_link_count`, `evidence_refs`, `review_required=None`, `threshold_policy=None`. Không tự chọn lookback 30/90 ngày: window là toàn lát nguồn visible được khai báo với mốc bắt đầu thực của release; ngày min/max observed không thay cho coverage bounds. Không cần join bảng customers chỉ để lấy PII khi customer_id từ orders đã đủ cho count; có thể kiểm missing-link riêng và giữ unknown, không lặng lẽ gán zero. Customer/other-shop history không được tiết lộ cho shop; unknown_link_count chỉ phản ánh phần dữ liệu caller được phép xem.

Tín hiệu hỗ trợ người xem kiểm tra lý do/bằng chứng, không phải fraud score/verdict. Không gán `fraud=True`, không suy tỷ lệ gian lận từ số request, không tự deny coins/refund, không đổi fault A2 và không tự block customer/shop. Hủy đơn (`orders.cancelled_at` hoặc cancel workflow runtime), yêu cầu trả hàng (`returns`) và scan logistics returning/returned/return_failed là ba loại sự kiện khác nhau; không cộng chung thành “số lần hoàn hàng”. Request bị rejected vẫn là một request, chưa chứng minh hàng thực sự đã trả. Muốn count hàng đã nhận lại cần thêm bằng chứng/timestamp được xác định, không dùng tên bảng để suy ra.

Huy đã chọn hiển thị số lần có bằng chứng để shop tự đánh giá. Không đặt ngưỡng “nhiều lần”, không phát nhãn/cảnh báo “nghi vấn gian lận”, không mô hình scoring và không tự yêu cầu review. Shop chỉ thấy request/đơn thuộc shop của mình cho customer của order đang xem. Trúc sở hữu UI/API hiển thị, Huy cung cấp count/window/provenance và authorized read interface; không thêm notification provider. Nếu tương lai muốn thay thành rule cảnh báo thì đó là thay đổi policy riêng, không nằm trong scope được chọn hiện tại.

Khuyến nghị permission check theo từng request và quan hệ seller→order dựa trên nguyên tắc least privilege/deny by default của [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html). Việc count không chứng minh fraud là giới hạn suy luận từ schema hiện tại, không phải kết luận khoa học hay policy fraud được trích từ nguồn đó.

Expected scenarios bổ sung: future return không tăng count; cùng order hai return row cho request_count=2/order_count=1; order của seller khác không lộ count/evidence; thiếu order/customer link trả coverage unknown thay vì gán khách bằng phone; status/refund sau as-of không lộ; canceled order không tự tăng return_count; count cao không thay eligibility coins hoặc biến `review_required=None` thành true khi chưa có rule. Đây là scenario chưa chạy test.
