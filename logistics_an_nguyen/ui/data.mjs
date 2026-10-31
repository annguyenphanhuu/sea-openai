// This adapter only reads A2 output. It never derives logistics or approval facts.
export const STATUSES = Object.freeze({
    exception: "Ngoại lệ",
    unknown_feed: "Thiếu dữ liệu",
    customer_fault: "Lỗi khách hàng",
    late: "Đang trễ",
    at_risk: "Nguy cơ trễ",
    watch: "Cần theo dõi",
    slow_safe: "Chậm, còn kịp hạn",
    on_track: "Đúng tiến độ",
});
export const FAULTS = Object.freeze({
    customer: "Khách hàng", carrier: "Đơn vị vận chuyển", seller: "Người bán", platform: "Nền tảng",
    force_majeure: "Bất khả kháng", unknown: "Chưa xác định",
});
const REASONS = Object.freeze({
    guaranteed_day_exceeded: "Đã quá ngày cam kết",
    delivery_confirmed: "Đã có bằng chứng giao hàng",
    eta_from_structured_evidence: "Dự kiến từ bằng chứng có cấu trúc",
    eta_missing: "Chưa có dự kiến giao mới",
    eta_expired: "Dự kiến trước đã hết hiệu lực",
    confidence_missing: "Chưa có mức tin cậy",
    risk_estimate_missing: "Chưa đủ dữ liệu ước tính nguy cơ",
    unstructured_text_unverified: "Có nội dung chưa được xác minh",
    "cod_refusal_risk:high": "Nguy cơ từ chối nhận COD: cao",
    "cod_refusal_risk:medium": "Nguy cơ từ chối nhận COD: vừa",
    seller_handover_on_time: "Shop bàn giao đúng hạn",
    seller_handover_late: "Shop bàn giao quá hạn chuẩn bị hàng",
    seller_handover_unverified: "Chưa đủ bằng chứng thời hạn bàn giao",
    "lsr_exempt:carrier": "Miễn trừ LSR",
    linehaul_report_missing: "Chưa có báo cáo chuyến tại thời điểm đánh giá",
});
const FORMAT_DATE = new Intl.DateTimeFormat("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "2-digit", year: "numeric",
});
const FORMAT_TIME = new Intl.DateTimeFormat("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const instant = (value) => typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));

export function formatDay(value) {
    // Guaranteed dates are calendar dates in Vietnam, never converted through UTC.
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return "Chưa xác định";
    const [year, month, day] = value.split("-");
    return `${day}/${month}/${year}`;
}

export function formatInstant(value) {
    if (!instant(value)) return { date: "Chưa xác định", time: "" };
    return { date: FORMAT_DATE.format(new Date(value)), time: FORMAT_TIME.format(new Date(value)) };
}

export function reasonLabel(code) {
    if (own(REASONS, code)) return REASONS[code];
    if (code.startsWith("status:")) return STATUSES[code.slice(7)] || code;
    if (code.startsWith("fault:")) return `Trách nhiệm: ${FAULTS[code.slice(6)] || code.slice(6)}`;
    if (code.startsWith("feed_")) return `Cần kiểm tra nguồn: ${code.split(":").at(-1)}`;
    if (code.startsWith("conflicting_fact:")) return `Dữ kiện mâu thuẫn: ${code.slice(17)}`;
    if (code.startsWith("untrusted_fact:")) return `Dữ kiện chưa đủ tin cậy: ${code.slice(15)}`;
    return code;
}

export function causeLabels(order) {
    const codes = order.cause.reason_codes.filter((code) => !code.startsWith("status:") && !code.startsWith("fault:"));
    return codes.length ? codes.map(reasonLabel) : ["Chưa có nguyên nhân được xác định"];
}

export function codRefusalBadge(order) {
    // Display the assessed reason; the browser never reimplements the risk rule.
    if (order.reason_codes.includes("cod_refusal_risk:high")) {
        return { level: "high", label: "Nguy cơ từ chối COD: cao" };
    }
    if (order.reason_codes.includes("cod_refusal_risk:medium")) {
        return { level: "medium", label: "Nguy cơ từ chối COD: vừa" };
    }
    return null;
}

export function lsrExemptionBadge(order) {
    return order.reason_codes.includes("lsr_exempt:carrier") ? "Miễn trừ LSR" : null;
}

export function resolveEvidence(payload, order) {
    // Resolve before filtering/sorting. Never follow a source-supplied URL.
    const match = /^#\/orders\/(0|[1-9]\d*)\/evidence$/.exec(order.evidence_ref);
    if (!match) throw new Error("Tham chiếu bằng chứng không hợp lệ.");
    const referenced = payload.orders[Number(match[1])];
    if (!referenced || referenced.order_id !== order.order_id) {
        throw new Error("Bằng chứng không thuộc đúng đơn hàng.");
    }
    return referenced.evidence;
}

export function validatePayload(payload) {
    const invalid = () => { throw new Error("Dữ liệu đơn hàng không đúng cấu trúc A2."); };
    if (!payload || payload.payload_version !== "a2_order_list_v1" || !instant(payload.tick_at)
        || !Array.isArray(payload.orders) || !Array.isArray(payload.feed_health)) invalid();
    const ids = new Set();
    for (const order of payload.orders) {
        if (!order || typeof order.order_id !== "string" || !order.order_id || ids.has(order.order_id)
            || !own(STATUSES, order.status) || !own(FAULTS, order.fault_party)
            || !instant(order.assessed_at) || Date.parse(order.assessed_at) !== Date.parse(payload.tick_at)
            || typeof order.guaranteed_date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(order.guaranteed_date)
            || !Number.isFinite(Date.parse(`${order.guaranteed_date}T00:00:00Z`))
            || new Date(`${order.guaranteed_date}T00:00:00Z`).toISOString().slice(0, 10) !== order.guaranteed_date
            || !(order.revised_eta === null || instant(order.revised_eta))
            || !Number.isInteger(order.late_days) || order.late_days < 0
            || !Number.isInteger(order.priority) || order.priority < 1 || order.priority > 8
            || !(order.customer_id === null || typeof order.customer_id === "string")
            || ![null, "COD", "PREPAID"].includes(order.payment)
            || !Array.isArray(order.reason_codes) || !order.reason_codes.every((code) => typeof code === "string")
            || !order.cause || order.cause.fault_party !== order.fault_party
            || JSON.stringify(order.cause.reason_codes) !== JSON.stringify(order.reason_codes)
            || !Array.isArray(order.evidence) || !Array.isArray(order.metadata_evidence)) invalid();
        ids.add(order.order_id);
        resolveEvidence(payload, order);
        for (const evidence of [...order.evidence, ...order.metadata_evidence]) {
            if (!evidence || !instant(evidence.ingested_at) || Date.parse(evidence.ingested_at) > Date.parse(payload.tick_at)
                || typeof evidence.is_structured !== "boolean"
                || !["feed", "source_table", "record_id", "fact_code"].every((key) => typeof evidence[key] === "string")) invalid();
        }
    }
    for (const health of payload.feed_health) {
        if (!health || typeof health.feed !== "string" || typeof health.usable_at_tick !== "boolean"
            || !["trusted", "stale", "corrupt", "missing"].includes(health.status)
            || !["source_timestamp", "checked_at", "last_ingested_at"].every((key) => health[key] === null || instant(health[key]))) invalid();
    }
    return payload;
}

export async function loadOrders({ mode = "sample", signal, fetcher = fetch } = {}) {
    if (!["sample", "api"].includes(mode)) throw new Error("Nguồn dữ liệu không hợp lệ.");
    const url = mode === "api" ? "/api/orders" : new URL("../sample_orders.json", import.meta.url).href;
    const response = await fetcher(url, { signal, credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`Không tải được ${mode === "api" ? "API đơn hàng" : "file mẫu"} (HTTP ${response.status}).`);
    return validatePayload(await response.json());
}

export function filterOrders(orders, { search = "", status = "", payment = "", sort = "priority" } = {}) {
    const query = search.trim().toLocaleLowerCase("vi");
    return orders.filter((order) => (!query || `${order.order_id} ${order.customer_id || ""}`.toLocaleLowerCase("vi").includes(query))
        && (!status || order.status === status)
        && (!payment || (payment === "unknown" ? order.payment === null : order.payment === payment)))
        .sort((a, b) => (sort === "priority" ? a.priority - b.priority : sort === "late_days" ? b.late_days - a.late_days : 0)
            || a.order_id.localeCompare(b.order_id));
}
