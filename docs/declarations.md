# Declarations — SEA OpenAI

**Ascendant · An Nguyên, Huy, Trúc · 31/10/2026**<br>
[Repo bài thi](https://github.com/annguyenphanhuu/sea-openai) · [Demo](https://sea-openai-ops-559aa5.azurewebsites.net/)

## 1. Dự án và tài liệu đã có trước hackathon

Nhóm đã chuẩn bị và diễn tập tại [vinhhuy12/sea-openai-hackathon](https://github.com/vinhhuy12/sea-openai-hackathon) trước sự kiện. Repo đó có nghiên cứu, ý tưởng ba agent, bản đăng ký, đặc tả, kế hoạch, prompt, bộ sinh dữ liệu và code tập dượt. **Khai báo của nhóm: không chép code giải pháp từ repo tập dượt vào repo thi; chỉ dùng ý tưởng, kế hoạch và bài học thiết kế.** Mã tập dượt không được tính là sản phẩm viết trong ngày. Lịch sử Git của repo thi là bằng chứng thời điểm thêm tệp, không tự chứng minh nguồn gốc từng dòng mã.

**Dữ liệu được tái sử dụng, có khai báo riêng:** `release_main/core_14d.sqlite` và `ops_14d.sqlite` được script Python của nhóm sinh trước sự kiện bằng seed cố định. Toàn bộ người, đơn và doanh nghiệp là tổng hợp/hư cấu. Đơn tạo 18–31/10/2026, scan/lần giao tiếp tục đến 08/11; một số bảng còn có bản ghi đến 10/11. Đây không phải dữ liệu nội bộ Shopee. Câu ticket gốc do Claude tạo, script điền dữ kiện thuộc bộ tổng hợp và biến thể ngôn ngữ. Bộ sinh dữ liệu và mã tập dượt không đưa vào repo giải pháp. [Tài liệu dữ liệu nguồn](https://github.com/vinhhuy12/sea-openai-hackathon/blob/main/data/release_main/DATA.md) và `manifest.sha256` đi cùng bản release được cung cấp riêng; kiểm định trong [docs/data_audit.md](https://github.com/annguyenphanhuu/sea-openai/blob/main/docs/data_audit.md).

Ánh xạ địa giới trong dữ liệu dựa trên [quangtam/vietnam-address-database](https://github.com/quangtam/vietnam-address-database). NOTICE của bộ sinh ghi MIT theo metadata/README upstream, upstream không có tệp LICENSE ở lần kiểm tra 23–24/10; nguồn này ghi công [thanhtrungit97/dvhcvn](https://github.com/thanhtrungit97/dvhcvn), nơi chưa khai giấy phép. Đây là khai báo provenance dữ liệu, không coi toàn bộ dữ liệu là do nhóm sáng tạo độc quyền.

Các bộ τ²-bench, Bitext, DataCo, Olist và AIOpsLab từng xuất hiện trong phương án đăng ký; **không dùng làm dữ liệu đầu vào của demo hiện tại**. Không lấy số đo của bản tập dượt làm kết quả ngày thi. Đáp án `truth/`/heldout không phải đầu vào agent.

## 2. Phần làm riêng trong hackathon 31/10

Repo thi bắt đầu ở **`25131a2` lúc 09:09:30 +07:00**, chỉ có README một dòng; scaffold **`919fef3` lúc 09:53:09**. Đối chiếu đến **`b00d78e` lúc 14:47:50**, các phần xây trong ngày gồm:

| Phạm vi | Thư mục bằng chứng |
| --- | --- |
| Hợp đồng, tham số, schema; runtime SQLite, replay/NEXT, A3 và cổng thực thi | `contracts/`, `requirements/`, `platform_huy/` |
| Đánh giá logistics A2, ETA, bằng chứng và danh sách đơn | `logistics_an_nguyen/` |
| Chăm sóc A1, luật hội thoại, xác nhận hủy, handoff và chọn câu | `care_truc/` |
| Web/API tích hợp, frontend, đóng gói triển khai | `platform_huy/serve_ui.py`, `platform_huy/ui_prototype/`, `frontend/`, `deploy/` |
| Kiểm thử, tài liệu bài thi và evidence | `acceptance_huy/`, `acceptance_an_nguyen/`, `acceptance_truc/`, `care_truc/tests/`, `docs/`, `.scratch/` |

Voice còn đang làm; voucher chưa được chứng minh xuyên suốt qua chat A1. Quyền lợi demo chỉ ghi runtime nội bộ; không chi tiền thật hoặc dùng ví Shopee. Tài liệu này không tính tính năng chưa kiểm chứng là đã hoàn thành.

<div class="page-break"></div>

## 3. Công cụ, dịch vụ và OSS

**Khai báo vai trò trong ngày thi:** Codex viết code, viết/chạy test và thực hiện deploy theo nhiệm vụ; subagent/worktree chia phạm vi, review độc lập trước tích hợp khi phù hợp. Claude chỉ đọc, review và viết prompt, **không chạm code giải pháp**. Việc Claude tạo câu ticket trước sự kiện là hoạt động chuẩn bị dữ liệu đã khai ở mục 1. Không suy ra tác giả từng dòng chỉ từ tên người commit.

OpenAI API là dịch vụ chọn mã câu có giới hạn cho A1; model cấu hình tại snapshot mặc định `gpt-5.4-mini`, có thể đổi qua môi trường. Microsoft Azure App Service là nơi cung cấp link demo. Công cụ AI và dịch vụ cloud không phải mã nguồn do nhóm sở hữu. Bộ bài nộp Markdown được chuyển sang HTML rồi Microsoft Edge headless in PDF.

| Thành phần OSS dùng trực tiếp | Vai trò / khai báo giấy phép |
| --- | --- |
| Python, SQLite | Nền chạy và lưu trữ; Python theo PSF, SQLite public domain. |
| `pytest==9.0.3`, `httpx==0.28.1` | Test và HTTP/OpenAI; MIT, BSD-3-Clause. |
| `huggingface-hub==1.16.4` trong `deploy/requirements.txt` | Adapter tải release/fallback trong repo; Apache-2.0. Không đồng nghĩa demo được host trên Hugging Face. |
| Next.js 16.4.3, React/React DOM 19.3.0 | Frontend riêng; MIT. |
| Fluent UI, Griffel, Phosphor Icons, Tailwind CSS, PostCSS, Zod | UI, style, biểu tượng và validation; MIT theo lockfile. |
| TypeScript, Playwright; ESLint và `@types/*` | Build/test/typecheck; TypeScript và Playwright Apache-2.0, ESLint và các gói `@types` trực tiếp MIT. |
| Python-Markdown, pypdf, PyMuPDF | Công cụ xuất/kiểm tra tài liệu tại máy soạn, không thêm dependency cho ứng dụng; lần lượt BSD-3-Clause, BSD-3-Clause, AGPL-3.0 hoặc giấy phép thương mại của nhà cung cấp. |

Danh mục phụ thuộc trực tiếp và bắc cầu của frontend cùng trường license nằm trong [frontend/package-lock.json](https://github.com/annguyenphanhuu/sea-openai/blob/main/frontend/package-lock.json); Python khai ở [requirements/](https://github.com/annguyenphanhuu/sea-openai/tree/main/requirements) và [deploy/requirements.txt](https://github.com/annguyenphanhuu/sea-openai/blob/main/deploy/requirements.txt). Giữ giấy phép/thông báo của từng gói khi phân phối chúng; repo này không chuyển quyền sở hữu OSS thành mã tự viết. Không khai một giấy phép chung mới cho toàn bộ dự án.

**Phạm vi khai báo:** nội dung dựa trên tài liệu nguồn, repo thực và xác nhận của nhóm; không phải chứng nhận độc lập về tuân thủ cuộc thi hay nguồn gốc toàn bộ mã. [Nhật ký Codex và các mốc kiểm chứng](https://github.com/annguyenphanhuu/sea-openai/blob/main/docs/codex-log.md) ghi rõ giới hạn bằng chứng.
