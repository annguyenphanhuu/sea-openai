# Ghi nhớ quyết định demo Huy — 31/10/2026

Tệp này lưu chỉ dẫn trên đĩa cho phiên sau đọc; không chứng minh phiên khác đã đọc hoặc tự kích hoạt bộ nhớ ẩn. Ưu tiên DEMO-FIRST và hoàn tất phần Huy trước. Dùng Superpowers, nghiên cứu trước khi quyết định, review độc lập bằng context sạch rồi lập implementation plan. Hỏi Huy trước khi triển khai hành vi còn chưa chốt. Spec ở `.scratch/specs/`, plan ở `.scratch/plans/`, research ở `.scratch/research/`.

## Đã xác nhận

- Xu bù: 5% giá trị hàng, làm tròn xuống bội 1.000; tối thiểu 10.000, tối đa 1.000.000; giá trị `None` hoặc `0` trả 10.000. Công thức chỉ tính khoản, không tự quyết điều kiện cấp.
- Demo chỉ cấp quyền lợi trong SQLite runtime nội bộ; không cộng ví Shopee thật hoặc gọi nhà cung cấp tài chính.
- Đồng hồ mô phỏng tiến thủ công bằng NEXT, mỗi tick đúng +30 phút. Chat xử lý ngay tại thời điểm mô phỏng hiện tại; giờ máy chủ chỉ ghi audit, không làm replay tự tiến hoặc quyết định freshness nghiệp vụ.
- Voucher 10.000 VND và xu dùng cùng điều kiện: trễ ít nhất hai ngày lịch Việt Nam, khách tự yêu cầu bằng TEXT trong chat do A1 mở, không lỗi khách và không bất khả kháng. Cấp cả voucher và xu thành hai khoản riêng; tối đa một lần mỗi loại cho mỗi đơn, không gộp voucher vào ledger xu hoặc để khoản này chặn khoản kia.
- Phạm vi là cấp quyền lợi nội bộ, không mô phỏng sử dụng voucher. Đổi/dùng voucher và hạn hết hiệu lực nằm ngoài phạm vi trừ khi Huy bổ sung; không tự tạo TTL hoặc mức chi tối thiểu.
- Huy hoặc nhân viên có thẩm quyền được xác minh bằng chứng lỗi/bất khả kháng theo từng đơn và ghi quyết định runtime có audit để chạy ca demo được cấp. Việc này không bỏ qua điều kiện khác, thẩm quyền, nguồn gốc bằng chứng, freshness, số tiền hoặc idempotency; không sửa DB nguồn.
- Shop chỉ xem bằng chứng mô tả thuộc shop của mình, gồm số lượng đơn/lượt trả hàng theo dữ liệu có thật. Không biến thống kê trả hàng thành kết luận gian lận.
- D1–D5 tiếp tục theo [docs/decisions.md](../../docs/decisions.md) và [docs/team_plan.md](../../docs/team_plan.md); không tự thay luật ngày cam kết, feed/heartbeat, text xin xu hoặc DB bất biến.
- Dùng nhánh `huy` hiện có theo yêu cầu trực tiếp, ưu tiên hơn quy tắc prefix chung. Fetch remote team, hợp nhất cập nhật nhánh và `upstream/main` trước khi làm/push. Không cài hooks; không merge/push main khi chưa được yêu cầu.

## Ánh xạ lịch sử — đề xuất cần review kỹ thuật

- Đối soát lịch sử theo từng kind, bám quy tắc giới hạn độc lập đã chốt: voucher lịch sử đã nhận diện không tiêu lượt coins. Review mapping kind nguồn sang quyền lợi runtime; kind chưa nhận diện cần làm rõ mapping, không tự gộp các loại.
- Không hỏi lại các lựa chọn đã xác nhận ở trên. Chỉ hỏi Huy khi xuất hiện quyết định nghiệp vụ/demo thực sự chưa được chốt.

## Latest execution authorization

- Controller may merge/push main for the requested integration; workers may not.
- Canonical benefit keys: xu:{order_id}, voucher:{order_id}. Each kind once/order.
- Task 3 handles clock/checkpoint only; Task 4 integrates A3/A2/guard. Run Task 1 alone, Task 2, pairs 3+5 / 6+7 / 4+8, then Task 9, with private worktrees and at most two implementation workers.
- Task-owned acceptance_huy tests are explicitly authorized. contracts and other owner code remain read-only.
- Full research and real RED/GREEN receipts stay in .scratch. Stop each task at 30 minutes; notify Huy at 13:00 VN if Tasks 1-4 are incomplete.

## Pending decision

- Fixed benefit key after a blocked attempt: audit denial and permit reconsideration before first grant, or permanently lock even a denied key. Asked Huy; Task 6 must not choose silently.

## Financial retry policy confirmed

Huy explicitly chose success-only reservation of xu:{order_id} and voucher:{order_id}. Denied attempts retain audit evidence but do not lock the canonical key. After verification, the same key is eligible for a new full evaluation; successful keys always replay their original receipt. This resolves the pending decision above. Task 6 may proceed under this policy.

## SQLite-only Space runtime confirmed

Huy explicitly removed MongoDB from the project. Revert merge PR #8 with `git revert -m 1 76abd17`; verify the repository tests in an environment without PyMongo. Keep existing local audit logs untracked when reverting the PR's unrelated log-removal changes.

StateStore has only a SQLite implementation; do not implement MongoStateStore or add a remote persistence backend. Runtime state lives on the Space's local disk. Returning to the baseline after a Space restart is acceptable for this demo; persistence across Space restarts is not a requirement. This does not weaken transactions, retry protection or receipts within an active run and does not permit changing source databases.

The user calls these changes deployment-plan step 2 (replace with the revert and tests) and step 5 (remove MongoStateStore entirely). The referenced numbered deployment plan has not been located in this checkout; its path has been requested. Do not replace Task 2 or Task 5 of the separate nine-task platform plan, which concern the reader and provenance respectively.
