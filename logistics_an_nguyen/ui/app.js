import { STATUSES, FAULTS, causeLabels, filterOrders, formatDay, formatInstant, loadOrders, reasonLabel, resolveEvidence } from "./data.mjs";

const $ = (id) => document.getElementById(id);
const mode = new URLSearchParams(location.search).get("source") || "sample";
let payload = null;
let expanded = null;

function node(tag, text = null, className = "") {
    const element = document.createElement(tag);
    if (text !== null) element.textContent = String(text);
    if (className) element.className = className;
    return element;
}

function timestamp(value) {
    const formatted = formatInstant(value);
    return formatted.time ? `${formatted.time} · ${formatted.date}` : formatted.date;
}

function cell(label, content, className = "") {
    const element = node("td", null, className);
    element.append(node("span", label, "field-label"));
    element.append(typeof content === "string" ? node("span", content) : content);
    return element;
}

function dateCell(label, value, calendar = false) {
    const content = node("div", null, value ? "date-value" : "muted");
    const formatted = calendar ? { date: formatDay(value), time: "" } : formatInstant(value);
    content.append(node("span", formatted.date));
    if (formatted.time) content.append(node("small", formatted.time, "secondary-value"));
    return cell(label, content);
}

function evidenceTable(evidence) {
    const wrap = node("div", null, "evidence-table-wrap");
    wrap.tabIndex = 0;
    wrap.setAttribute("aria-label", "Bảng bằng chứng, có thể cuộn");
    const table = node("table", null, "evidence-table");
    const head = node("thead");
    const headings = node("tr");
    for (const title of ["Dữ kiện", "Giá trị", "Nguồn / Bản ghi", "Đã ghi nhận lúc", "Loại bằng chứng"]) {
        const th = node("th", title); th.scope = "col"; headings.append(th);
    }
    head.append(headings);
    const body = node("tbody");
    for (const item of evidence) {
        const row = node("tr");
        const fact = node("td"); fact.append(node("code", item.fact_code));
        const value = node("td", item.value === null ? "null" : String(item.value));
        const source = node("td");
        source.append(node("code", `${item.source_table} / ${item.record_id}`), node("span", item.feed, "secondary-value"));
        row.append(fact, value, source, node("td", timestamp(item.ingested_at)), node("td", item.is_structured ? "Có cấu trúc" : "Nội dung chưa xác minh"));
        body.append(row);
    }
    table.append(head, body); wrap.append(table);
    return wrap;
}

function closeEvidence(orderId) {
    expanded = null;
    render();
    document.querySelectorAll(".verify-button").forEach((button) => {
        if (button.dataset.orderId === orderId) button.focus();
    });
}

function evidencePanel(order, index) {
    const tr = node("tr", null, "evidence-row");
    const td = node("td"); td.colSpan = 9;
    const panel = node("section", null, "evidence-panel");
    panel.id = `evidence-${index}`;
    panel.setAttribute("aria-labelledby", `evidence-title-${index}`);
    const heading = node("div", null, "evidence-heading");
    const intro = node("div");
    const title = node("h2", `Bằng chứng · ${order.order_id}`); title.id = `evidence-title-${index}`;
    intro.append(title, node("p", "Đối chiếu dữ kiện nguồn với kết luận A2. Mở xem không ghi nhận phê duyệt hay thay đổi đánh giá."));
    const close = node("button", "Đóng bằng chứng", "secondary"); close.type = "button";
    close.addEventListener("click", () => closeEvidence(order.order_id));
    heading.append(intro, close); panel.append(heading);
    const meta = node("div", null, "evidence-meta");
    for (const [label, value] of [["Đánh giá lúc (giờ VN)", timestamp(order.assessed_at)], ["Bên chịu trách nhiệm", FAULTS[order.fault_party]], ["Tham chiếu trong snapshot", order.evidence_ref]]) {
        const item = node("div"); item.append(node("strong", label), node("span", value)); meta.append(item);
    }
    panel.append(meta, node("h3", "Các căn cứ của kết luận"));
    const reasons = node("ul", null, "code-list");
    for (const code of order.cause.reason_codes) {
        const item = node("li"); item.append(node("span", `${reasonLabel(code)} · `), node("code", code)); reasons.append(item);
    }
    panel.append(reasons, node("h3", "Bằng chứng đánh giá"), evidenceTable(resolveEvidence(payload, order)));
    panel.append(node("h3", "Nguồn của ngày đặt, bàn giao và thanh toán"), evidenceTable(order.metadata_evidence));
    panel.append(node("h3", "Tình trạng nguồn tại thời điểm đánh giá"));
    const feeds = node("ul", null, "feed-list");
    for (const health of payload.feed_health) {
        const item = node("li");
        item.append(node("strong", health.feed), node("span", `${health.status} · ${health.usable_at_tick ? "Dùng được tại tick này" : "Không dùng được tại tick này"}`),
            node("span", `Mốc nguồn: ${timestamp(health.source_timestamp)}`), node("span", `Kiểm tra: ${timestamp(health.checked_at)}`));
        feeds.append(item);
    }
    panel.append(feeds, node("p", "Đây là tình trạng nguồn của snapshot. Quyền liên hệ hoặc thực thi phải được hệ thống kiểm tra lại tại thời điểm xử lý.", "evidence-note"));
    const raw = node("details");
    raw.append(node("summary", "Xem dữ liệu gốc của đơn (JSON)"), node("pre", JSON.stringify(order, null, 2)));
    panel.append(raw); td.append(panel); tr.append(td);
    return tr;
}

function render() {
    if (!payload) return;
    const filters = { search: $("search").value, status: $("status-filter").value, payment: $("payment-filter").value, sort: $("sort").value };
    const orders = filterOrders(payload.orders, filters);
    if (!orders.some((order) => order.order_id === expanded)) expanded = null;
    $("orders-body").replaceChildren();
    const fragment = document.createDocumentFragment();
    orders.forEach((order) => {
        const index = payload.orders.indexOf(order);
        const isOpen = expanded === order.order_id;
        const row = node("tr", null, `order-row${isOpen ? " selected" : ""}`);
        const identity = node("th"); identity.scope = "row";
        identity.append(node("span", order.order_id, "order-id"), node("small", order.customer_id || "Chưa có mã khách", "secondary-value"));
        const status = node("span", STATUSES[order.status], `status status-${order.status}`); status.title = order.status;
        const cause = node("div");
        const causes = causeLabels(order);
        cause.append(node("span", causes[0]));
        if (causes.length > 1) cause.append(node("small", causes.slice(1).join(" · "), "secondary-value"));
        const late = node("span", `${order.late_days} ngày`, `late-value${order.late_days ? " is-late" : ""}`);
        const payment = order.payment === "PREPAID" ? "Trả trước" : order.payment || "Chưa rõ";
        const button = node("button", isOpen ? "Đóng bằng chứng" : "Xác minh bằng chứng", "verify-button");
        button.type = "button";
        button.dataset.orderId = order.order_id;
        button.setAttribute("aria-expanded", String(isOpen));
        button.setAttribute("aria-label", `${isOpen ? "Đóng" : "Xác minh"} bằng chứng đơn ${order.order_id}`);
        if (isOpen) button.setAttribute("aria-controls", `evidence-${index}`);
        button.addEventListener("click", () => {
            expanded = isOpen ? null : order.order_id;
            render();
            document.querySelectorAll(".verify-button").forEach((current) => {
                if (current.dataset.orderId === order.order_id) current.focus({ preventScroll: true });
            });
        });
        row.append(identity, cell("Trạng thái", status), dateCell("Ngày cam kết", order.guaranteed_date, true),
            dateCell("Dự kiến mới", order.revised_eta), cell("Nguyên nhân", cause), cell("Bên chịu trách nhiệm", FAULTS[order.fault_party]),
            cell("Ngày trễ", late), cell("Thanh toán", payment), cell("Bằng chứng", button));
        fragment.append(row);
        if (isOpen) fragment.append(evidencePanel(order, index));
    });
    $("orders-body").append(fragment);
    $("result-count").textContent = `Hiển thị ${orders.length} / ${payload.orders.length} đơn hàng`;
    $("footer-count").textContent = `${orders.length} đơn trong danh sách`;
    $("table-wrap").hidden = orders.length === 0;
    $("empty").hidden = orders.length !== 0;
    $("clear-filters").hidden = !filters.search && !filters.status && !filters.payment;
}

async function reload() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    payload = null; expanded = null;
    $("reload").disabled = true;
    $("filters").querySelectorAll("input, select").forEach((control) => { control.disabled = true; });
    $("loading").hidden = false;
    $("load-error").hidden = true;
    $("table-wrap").hidden = true;
    $("empty").hidden = true;
    $("clear-filters").hidden = true;
    $("result-count").textContent = "Đang tải danh sách…";
    $("snapshot").textContent = "Đang đọc thời điểm đánh giá…";
    $("footer-count").textContent = "";
    $("orders-region").setAttribute("aria-busy", "true");
    try {
        payload = await loadOrders({ mode, signal: controller.signal });
        $("source-label").textContent = mode === "api" ? "Nguồn API đơn hàng" : `Dữ liệu mẫu · ${payload.orders.length} đơn`;
        $("snapshot").textContent = `Đánh giá lúc ${timestamp(payload.tick_at)}${mode === "sample" ? " · Snapshot mẫu" : ""}`;
        render();
    } catch (error) {
        const detail = error.name === "AbortError" ? "Quá thời gian chờ tải dữ liệu." : error instanceof SyntaxError ? "Nguồn trả về dữ liệu JSON không hợp lệ." : error.message;
        $("load-error").textContent = `${detail} ${mode === "api" ? "Kiểm tra kết nối API và quyền truy cập, rồi chọn Tải lại dữ liệu." : "Mở trang qua máy chủ HTTP và kiểm tra sample_orders.json, rồi chọn Tải lại dữ liệu."}`;
        $("load-error").hidden = false;
        $("result-count").textContent = "Chưa tải được danh sách";
        $("snapshot").textContent = "Chưa có snapshot để hiển thị";
    } finally {
        clearTimeout(timeout);
        $("reload").disabled = false;
        $("filters").querySelectorAll("input, select").forEach((control) => { control.disabled = !payload; });
        $("loading").hidden = true;
        $("orders-region").setAttribute("aria-busy", "false");
    }
}

for (const [value, label] of Object.entries(STATUSES)) {
    const option = node("option", label); option.value = value; $("status-filter").append(option);
}
$("source-label").textContent = mode === "api" ? "Nguồn API đơn hàng" : "Dữ liệu mẫu · 20 đơn";
$("filters").addEventListener("submit", (event) => event.preventDefault());
$("search").addEventListener("input", render);
for (const id of ["status-filter", "payment-filter", "sort"]) $(id).addEventListener("change", render);
$("clear-filters").addEventListener("click", () => {
    $("search").value = ""; $("status-filter").value = ""; $("payment-filter").value = "";
    render(); $("search").focus();
});
$("reload").addEventListener("click", reload);
reload();
