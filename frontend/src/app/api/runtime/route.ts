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
    return upstream(paths[kind], payload);
}
