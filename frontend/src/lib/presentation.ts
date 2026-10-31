import { statusLabels, statusSchema, type Runtime } from "./runtime";

export type Order = Runtime["orders"][number];
export type Session = Runtime["active_chats"][number];
export const statuses = statusSchema.options;
export { statusLabels };
export const sessionLabels: Record<string, string> = {
    active: "Đang trò chuyện", awaiting_cancel_confirmation: "Chờ xác nhận hủy", handoff_pending: "Đang chuyển nhân viên",
    transferred: "Đã chuyển nhân viên", completed: "Đã kết thúc", pending_delivery: "Chờ gửi lời mở đầu",
};
export const faultLabels: Record<string, string> = {
    carrier: "Đơn vị vận chuyển", seller: "Người bán", customer: "Khách hàng", force_majeure: "Bất khả kháng", unknown: "Chưa đủ căn cứ",
};
export const feedLabels: Record<string, string> = { trusted: "Đáng tin cậy", stale: "Quá hạn cập nhật", corrupt: "Dữ liệu lỗi", missing: "Thiếu dữ liệu" };
export const sourceLabels: Record<string, string> = { orders: "Thông tin đơn hàng", scan_events: "Sự kiện vận chuyển", driver_messages: "Thông tin tài xế", linehaul_reports: "Báo cáo tuyến trục", hub_capacity: "Công suất trung tâm", weather: "Thông tin thời tiết" };
export function sessionLabel(status: string) { return sessionLabels[status] ?? "Cần kiểm tra trạng thái"; }
export function formatDate(value: string | null | undefined, withTime = false) {
    if (!value) return "Chưa xác định";
    const instant = new Date(value);
    if (Number.isNaN(instant.valueOf())) return "Chưa xác định";
    return new Intl.DateTimeFormat("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "2-digit", year: "numeric", ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}) }).format(instant);
}
export const percent = (value: number) => `${Math.round(value * 100)}%`;
const reasonLabels: Record<string, string> = {
    guaranteed_day_exceeded: "Đã quá ngày giao cam kết.", eta_missing: "Chưa có dự báo giao hàng đã được xác minh.",
    eta_after_guaranteed_day: "Dự báo giao vượt ngày cam kết.", linehaul_report_missing: "Thiếu báo cáo tuyến vận chuyển để đối chiếu.",
    delivery_confirmed: "Có bằng chứng ghi nhận giao hàng trong dữ liệu nguồn.", seller_handover_on_time: "Người bán bàn giao đúng hạn.",
    seller_handover_late: "Người bán bàn giao sau hạn.", unstructured_text_unverified: "Nội dung tự do chưa được dùng làm căn cứ xác minh.",
};
export function reasons(order: Order) {
    const translated = [...new Set(order.reason_codes.flatMap(code => reasonLabels[code] ? [reasonLabels[code]] : []))];
    return translated.length ? translated : ["Xem đánh giá và bằng chứng của đơn để xác định bước xử lý phù hợp."];
}
export function isTerminal(status: string) { return ["transferred", "completed", "handoff_pending"].includes(status); }
