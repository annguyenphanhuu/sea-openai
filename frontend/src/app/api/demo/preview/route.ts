import { canPrepare, orders, previewRequestSchema } from "@/lib/demo";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
    const input = previewRequestSchema.safeParse(await request.json().catch(() => null));
    if (!input.success) return NextResponse.json({ error: "Yêu cầu không hợp lệ." }, { status: 400 });
    const { orderId, scenario, kind } = input.data;
    const order = orders.find((item) => item.id === orderId);
    if (!order) return NextResponse.json({ error: "Không tìm thấy đơn minh họa." }, { status: 404 });
    if (kind === "draft" && !canPrepare(order, scenario)) {
        return NextResponse.json({ error: "A3 hoặc dữ liệu đơn chưa cho phép chuẩn bị liên hệ chủ động." }, { status: 403 });
    }
    const message = kind === "handoff"
        ? `Đã xem trước yêu cầu chuyển nhân viên cho ${order.id}. Chưa tạo yêu cầu trong hệ thống thật.`
        : `Chào bạn ${order.name}, Chợ Phố đang kiểm tra đơn ${order.id}. ${order.reason} ${order.eta ? `Ngày dự kiến hiện tại là ${order.eta}. Đây là dự kiến, chưa phải cam kết giao mới.` : "Hiện chưa đủ dữ liệu để đưa ra ngày giao dự kiến."}`;
    return NextResponse.json({ kind, orderId, message, delivered: false, persisted: false }, { headers: { "Cache-Control": "no-store" } });
}
