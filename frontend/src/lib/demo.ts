import { z } from "zod";

// Demo-only DTO, not a replacement for contracts.types.OrderAssessment.
export const orderSchema = z.object({
    id: z.string(), name: z.string(), origin: z.string(), destination: z.string(),
    status: z.enum(["at_risk", "late", "unknown_feed", "on_track"]),
    eta: z.string().nullable(), due: z.string(), orderedAt: z.string().nullable(),
    handedOverAt: z.string().nullable(), probability: z.number().nullable(),
    confidence: z.number(), reason: z.string(), event: z.string(), eventAt: z.string(),
});
export type Order = z.infer<typeof orderSchema>;
export const scenarioSchema = z.enum(["healthy", "failure"]);
export type Scenario = z.infer<typeof scenarioSchema>;
export const snapshotSchema = z.object({
    mode: z.literal("demo"), scenario: scenarioSchema, contactGate: z.boolean(),
    orders: z.array(orderSchema), assessedAt: z.string(),
});
export type Snapshot = z.infer<typeof snapshotSchema>;
export const previewRequestSchema = z.object({
    orderId: z.string(), scenario: scenarioSchema, kind: z.enum(["draft", "handoff"]),
}).strict();
export const previewSchema = z.object({
    kind: z.enum(["draft", "handoff"]), orderId: z.string(), message: z.string(),
    delivered: z.literal(false), persisted: z.literal(false),
});
export type Preview = z.infer<typeof previewSchema>;

// Only the four illustrative records from the original UI. Never source data.
export const orders: Order[] = [
    { id: "DEMO-0281", name: "Nguyễn Minh Anh", origin: "Bình Tân", destination: "Đà Nẵng", status: "at_risk", eta: "30/10/2026", due: "29/10/2026", orderedAt: null, handedOverAt: null, probability: 82, confidence: 78, reason: "Chuyến trục chưa ghi nhận đến trung tâm đích.", event: "Đã xuất bến", eventAt: "10:45" },
    { id: "DEMO-0194", name: "Trần Hoàng Nam", origin: "Thủ Đức", destination: "Bình Thạnh", status: "late", eta: "29/10/2026", due: "27/10/2026", orderedAt: null, handedOverAt: null, probability: 100, confidence: 91, reason: "Đã hết ngày đảm bảo; chưa có bằng chứng giao thành công.", event: "Đến bưu cục", eventAt: "09:10" },
    { id: "DEMO-0342", name: "Lê Thu Hà", origin: "Hà Nội", destination: "Hải Phòng", status: "unknown_feed", eta: null, due: "29/10/2026", orderedAt: null, handedOverAt: null, probability: null, confidence: 35, reason: "Nguồn dữ liệu hãng vận chuyển chưa cập nhật đủ.", event: "Bàn giao hãng", eventAt: "08:30" },
    { id: "DEMO-0408", name: "Phạm Quốc Huy", origin: "Bình Tân", destination: "Quận 7", status: "on_track", eta: "28/10/2026", due: "28/10/2026", orderedAt: null, handedOverAt: null, probability: 8, confidence: 94, reason: "Kiện đang được giao trong ngày đảm bảo.", event: "Đang giao hàng", eventAt: "11:20" },
];
export const statusLabels: Record<Order["status"], string> = {
    at_risk: "Nguy cơ trễ", late: "Đang trễ", unknown_feed: "Thiếu dữ liệu", on_track: "Đúng tiến độ",
};
export function canPrepare(order: Order, scenario: Scenario) {
    return scenario === "healthy" && order.status !== "unknown_feed" && (order.probability ?? 0) >= 70;
}
export function getSnapshot(scenario: Scenario): Snapshot {
    return { mode: "demo", scenario, contactGate: scenario === "healthy", orders, assessedAt: "28/10/2026, 12:00" };
}
