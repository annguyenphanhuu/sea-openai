import { z } from "zod";

export const statusSchema = z.enum(["exception", "unknown_feed", "customer_fault", "late", "at_risk", "watch", "slow_safe", "on_track"]);
export const statusLabels: Record<z.infer<typeof statusSchema>, string> = {
    exception: "Ngoại lệ", unknown_feed: "Thiếu dữ liệu", customer_fault: "Lỗi khách hàng", late: "Đang trễ",
    at_risk: "Nguy cơ trễ", watch: "Theo dõi", slow_safe: "Chậm nhưng còn kịp", on_track: "Đúng tiến độ",
};
const orderSchema = z.object({
    order_id: z.string(), status: statusSchema, guaranteed_date: z.string(), revised_eta: z.string().nullable(),
    late_days: z.number(), late_probability: z.number(), confidence: z.number(), fault_party: z.string(),
    reason_codes: z.array(z.string()), evidence: z.array(z.unknown()),
    created_at: z.string().nullable().optional(), handed_over_at: z.string().nullable().optional(),
});
export const runtimeSchema = z.object({
    llm: z.object({ enabled: z.boolean(), model: z.string().nullable() }).optional(),
    inside: z.object({ used_llm: z.boolean(), codes: z.array(z.string()) }).optional(),
    mode: z.literal("local_integrated_web_inbox"), now: z.string(), guard_alive: z.boolean(),
    proactive_allowed: z.boolean(), orders: z.array(orderSchema), orders_total: z.number(),
    contact_queue_total: z.number(), phase_trace: z.array(z.string()),
    feed_health: z.array(z.object({ feed: z.string(), status: z.string(), source_timestamp: z.string().nullable() })),
    label_counts: z.record(z.string(), z.number()),
    selected_order_id: z.string().nullable(),
    chat: z.object({ session_id: z.string(), order_id: z.string(), status: z.string(),
        messages: z.array(z.object({ id: z.string(), kind: z.string(), text: z.string() })),
        pending: z.object({ reply_to: z.string() }).passthrough().nullable(),
    }).nullable(),
    active_chats: z.array(z.object({ session_id: z.string(), order_id: z.string(), status: z.string() })),
    ledger_total: z.number(), outbox_total: z.number(), handoffs: z.array(z.unknown()),
    ledger: z.array(z.unknown()), outbox: z.array(z.unknown()), cancellations: z.array(z.unknown()),
});
export type Runtime = z.infer<typeof runtimeSchema>;
export const commandSchema = z.discriminatedUnion("kind", [
    z.object({ kind: z.literal("next") }).strict(),
    z.object({ kind: z.literal("kill") }).strict(),
    z.object({ kind: z.literal("revive") }).strict(),
    z.object({ kind: z.literal("open"), order_id: z.string().min(1) }).strict(),
    z.object({ kind: z.literal("say"), session_id: z.string().min(1), text: z.string().trim().min(1).max(8000),
        request_id: z.string().uuid(), reply_to: z.string().optional() }).strict(),
]);
export type Command = z.infer<typeof commandSchema>;

export async function requestRuntime(input?: Command | { order_id?: string; session_id?: string }): Promise<Runtime> {
    const mutation = input && "kind" in input;
    const query = !mutation && input ? new URLSearchParams(input).toString() : "";
    const response = await fetch(`/api/runtime${query ? `?${query}` : ""}`, mutation ? {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
    } : { cache: "no-store" });
    const body: unknown = await response.json();
    if (!response.ok) {
        const error = z.object({ error: z.string() }).safeParse(body);
        throw new Error(error.success ? error.data.error : "Không thể kết nối pipeline.");
    }
    return runtimeSchema.parse(body);
}
