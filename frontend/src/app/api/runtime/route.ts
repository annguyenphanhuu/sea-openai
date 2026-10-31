import { NextResponse } from "next/server";
import { commandSchema, runtimeSchema } from "@/lib/runtime";

const paths = { next: "/api/next", kill: "/api/a3/kill", revive: "/api/a3/revive", open: "/api/chat/open", say: "/api/chat/say" };

function localRequest(request: Request) {
    const host = request.headers.get("host") || "";
    return /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i.test(host)
        && (!request.headers.has("x-forwarded-host") || request.headers.get("x-forwarded-host") === host)
        && !request.headers.has("forwarded");
}

async function upstream(path: string, payload?: object) {
    try {
        const base = new URL(process.env.PIPELINE_URL || "http://127.0.0.1:8765");
        if (!["http:", "https:"].includes(base.protocol)) throw new Error("Invalid pipeline URL");
        const response = await fetch(new URL(path, base), {
            method: payload ? "POST" : "GET", cache: "no-store", redirect: "error",
            headers: { "Content-Type": "application/json", ...(process.env.LIVE_PRESENTER_KEY ? { "X-Presenter-Key": process.env.LIVE_PRESENTER_KEY } : {}) },
            body: payload ? JSON.stringify(payload) : undefined, signal: AbortSignal.timeout(60000),
        });
        const body: unknown = await response.json();
        if (!response.ok) return NextResponse.json(body, { status: response.status });
        const parsed = runtimeSchema.safeParse(body);
        if (!parsed.success) return NextResponse.json({ error: "Pipeline trả dữ liệu không đúng định dạng." }, { status: 502 });
        return NextResponse.json(parsed.data, { headers: { "Cache-Control": "no-store" } });
    } catch {
        return NextResponse.json({ error: "Không kết nối được pipeline. Kiểm tra server Python và PIPELINE_URL." }, { status: 502 });
    }
}

export async function GET(request: Request) {
    if (!localRequest(request)) return NextResponse.json({ error: "Phòng điều hành chỉ dùng trên localhost." }, { status: 403 });
    const input = new URL(request.url).searchParams;
    const query = new URLSearchParams();
    for (const key of ["order_id", "session_id"]) {
        const value = input.get(key);
        if (value) query.set(key, value);
    }
    return upstream(`/api/demo/state?${query}`);
}

export async function POST(request: Request) {
    if (!localRequest(request)) return NextResponse.json({ error: "Phòng điều hành chỉ dùng trên localhost." }, { status: 403 });
    const origin = request.headers.get("origin");
    if (origin !== `http://${request.headers.get("host")}` && origin !== `https://${request.headers.get("host")}`) {
        return NextResponse.json({ error: "Yêu cầu phải đến từ giao diện cùng nguồn." }, { status: 403 });
    }
    if (Number(request.headers.get("content-length")) > 16384) return NextResponse.json({ error: "Yêu cầu quá lớn." }, { status: 413 });
    const input = commandSchema.safeParse(await request.json().catch(() => null));
    if (!input.success) return NextResponse.json({ error: "Lệnh không hợp lệ." }, { status: 400 });
    const { kind, ...payload } = input.data;
    if (kind === "say" && request.headers.get("accept")?.includes("application/x-ndjson")) {
        const requestId = input.data.request_id;
        const sessionId = input.data.session_id;
        const encoder = new TextEncoder();
        const stream = new ReadableStream<Uint8Array>({
            async start(controller) {
                let connected = true;
                const send = (event: object) => {
                    if (!connected) return;
                    try { controller.enqueue(encoder.encode(JSON.stringify(event) + "\n")); }
                    catch { connected = false; }
                };
                send({ kind: "acknowledged", request_id: requestId });
                send({ kind: "status", request_id: requestId, status: "processing" });
                try {
                    const response = await upstream(paths[kind], payload);
                    const body: unknown = await response.json();
                    if (!response.ok) throw new Error("Upstream unavailable");
                    const snapshot = runtimeSchema.parse(body);
                    if (!snapshot.chat || snapshot.chat.session_id !== sessionId) throw new Error("Session mismatch");
                    const reply = snapshot.chat.messages.find(message => message.kind === "response" && message.id === snapshot.turn_result?.message_id);
                    if (reply) send({ kind: "reply", request_id: requestId, message_id: reply.id, text: reply.text });
                    send({ kind: "done", request_id: requestId, snapshot });
                } catch {
                    send({ kind: "error", request_id: requestId, message: "Chưa xác nhận được kết quả. Gửi lại cùng yêu cầu để kiểm tra." });
                } finally {
                    if (connected) controller.close();
                }
            },
        });
        return new Response(stream, { headers: { "Content-Type": "application/x-ndjson; charset=utf-8", "Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no" } });
    }
    return upstream(paths[kind], payload);
}
