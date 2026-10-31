# Kiểm tra và đồng bộ thủ công

Theo yêu cầu Huy, team dùng ba nhánh `huy`, `an-nguyen`, `truc`; không cài hook hoặc bắt tên nhánh feat/chore. Các script hook, workflow GitHub và test riêng cho cơ chế đó đã được gỡ. Ownership và quy tắc nghiệp vụ trong AGENTS.md vẫn áp dụng.

Trước mỗi phần việc và trước khi push, kiểm tra working tree rồi đồng bộ repo team. Ví dụ với checkout Huy, remote team là upstream:

```powershell
git status --short --branch
git fetch upstream
git switch huy
git merge upstream/huy
git merge upstream/main
```

Giữ lại thay đổi chưa commit của mình trước khi merge; không reset hoặc force push để giải quyết conflict. Nếu dùng clone trực tiếp repo team, kiểm tra remote và thay upstream bằng origin khi phù hợp. An Nguyen/Trúc dùng nhánh cá nhân tương ứng.

Sau khi hoàn thành một phần, chạy:

```powershell
python -c "import contracts"
pytest -q
git diff --check
```

Stage đúng các file của phần việc, kiểm tra staged diff, commit và push nhánh cá nhân. Nếu remote có thêm commit trong lúc làm, fetch/merge rồi chạy lại các kiểm tra liên quan trước push. Chỉ merge và push main khi Huy yêu cầu.

Không stage `.env`, `data/`, `runs/`, `truth/` hoặc DB. Dữ liệu được chia sẻ riêng, luôn đọc nguồn ở chế độ read-only. Không còn tự copy ignored files khi tạo worktree.
