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
    turn_result: z.object({ message_id: z.string().nullable().optional(), text: z.string() }).optional(),
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
export type SayCommand = Extract<Command, { kind: "say" }>;
export type PendingTurn = {
    command: SayCommand;
    status: "sending" | "uncertain";
    reply: { id: string; text: string } | null;
    restored: boolean;
};
const streamEventSchema = z.discriminatedUnion("kind", [
    z.object({ kind: z.literal("acknowledged"), request_id: z.string() }),
    z.object({ kind: z.literal("status"), request_id: z.string(), status: z.literal("processing") }),
    z.object({ kind: z.literal("reply"), request_id: z.string(), message_id: z.string(), text: z.string() }),
    z.object({ kind: z.literal("done"), request_id: z.string(), snapshot: runtimeSchema }),
    z.object({ kind: z.literal("error"), request_id: z.string(), message: z.string() }),
]);
export type ChatStreamEvent = z.infer<typeof streamEventSchema>;

export async function readChatStream(response: Response, command: SayCommand, onEvent: (event: ChatStreamEvent) => void): Promise<Runtime> {
    if (!response.ok) throw new Error("Chưa xác nhận được kết quả. Gửi lại cùng yêu cầu để kiểm tra.");
    if (!response.headers.get("content-type")?.includes("application/x-ndjson")) {
        const snapshot = runtimeSchema.parse(await response.json());
        if (snapshot.chat?.session_id !== command.session_id) throw new Error("Hội thoại trả về không khớp yêu cầu.");
        return snapshot;
    }
    if (!response.body) throw new Error("Luồng trả lời không khả dụng.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8", { fatal: true });
    let buffer = "";
    let result: Runtime | null = null;
    const consume = (line: string) => {
        if (!line.trim()) return;
        if (result) throw new Error("Luồng trả lời có dữ liệu sau khi hoàn tất.");
        const event = streamEventSchema.parse(JSON.parse(line));
        if (event.request_id !== command.request_id) throw new Error("Luồng trả lời không khớp yêu cầu.");
        if (event.kind === "error") throw new Error(event.message);
        if (event.kind === "done") {
            if (event.snapshot.chat?.session_id !== command.session_id) throw new Error("Hội thoại trả về không khớp yêu cầu.");
            result = event.snapshot;
        }
        onEvent(event);
    };
    try {
        while (true) {
            const chunk = await reader.read();
            buffer += decoder.decode(chunk.value, { stream: !chunk.done });
            if (buffer.length > 4_000_000) throw new Error("Luồng trả lời vượt kích thước cho phép.");
            let newline = buffer.indexOf("\n");
            while (newline !== -1) {
                consume(buffer.slice(0, newline));
                buffer = buffer.slice(newline + 1);
                newline = buffer.indexOf("\n");
            }
            if (chunk.done) break;
        }
        consume(buffer);
        if (!result) throw new Error("Kết nối bị ngắt trước khi xác nhận kết quả. Gửi lại cùng yêu cầu để kiểm tra.");
        return result;
    } finally {
        await reader.cancel().catch(() => {});
        reader.releaseLock();
    }
}

export async function requestChat(command: SayCommand, onEvent: (event: ChatStreamEvent) => void): Promise<Runtime> {
    const response = await fetch("/api/runtime", {
        method: "POST", headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
        body: JSON.stringify(command),
        signal: AbortSignal.timeout(65000),
    });
    return readChatStream(response, command, onEvent);
}

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
