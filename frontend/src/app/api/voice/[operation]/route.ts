import { NextResponse } from "next/server";
import { voiceOperationSchema, voicePayloads, voiceResults } from "@/lib/voice-api";

export async function POST(request: Request, context: { params: Promise<{ operation: string }> }) {
    const host = request.headers.get("host") || "";
    const origin = request.headers.get("origin");
    const publicHost = process.env.FRONTEND_HOST;
    const allowedPublicHost = !!publicHost && host.toLowerCase() === publicHost.toLowerCase();
    if ((!allowedPublicHost && !/^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i.test(host))
        || (request.headers.has("x-forwarded-host") && request.headers.get("x-forwarded-host") !== host)
        || request.headers.has("forwarded") || (origin !== `http://${host}` && origin !== `https://${host}`)) {
        return NextResponse.json({ error: "Yêu cầu voice phải đến từ giao diện local." }, { status: 403 });
    }
    const operation = voiceOperationSchema.safeParse((await context.params).operation);
    if (!operation.success) return NextResponse.json({ error: "Chức năng voice không hợp lệ." }, { status: 404 });
    if (Number(request.headers.get("content-length")) > 16384) return NextResponse.json({ error: "Yêu cầu quá lớn." }, { status: 413 });
    const payload = voicePayloads[operation.data].safeParse(await request.json().catch(() => null));
    if (!payload.success) return NextResponse.json({ error: "Dữ liệu voice không hợp lệ." }, { status: 400 });
    try {
        const base = new URL(process.env.PIPELINE_URL || "http://127.0.0.1:8765");
        if (!["http:", "https:"].includes(base.protocol)) throw new Error("Invalid backend");
        const result = await fetch(new URL(`/api/voice/${operation.data}`, base), {
            method: "POST", cache: "no-store", redirect: "error", signal: AbortSignal.timeout(30000),
            headers: { "Content-Type": "application/json", ...(process.env.LIVE_PRESENTER_KEY ? { "X-Presenter-Key": process.env.LIVE_PRESENTER_KEY } : {}) },
            body: JSON.stringify(payload.data),
        });
        const body: unknown = await result.json();
        if (!result.ok) return NextResponse.json({ error: "Không thể thực hiện voice. Kiểm tra phiên, ngân sách hoặc cấu hình OpenAI." }, { status: result.status });
        const output = voiceResults[operation.data].safeParse(body);
        if (!output.success) throw new Error("Invalid voice response");
        return NextResponse.json(output.data, { headers: { "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" } });
    } catch {
        return NextResponse.json({ error: "Máy chủ voice chưa sẵn sàng. Chat text vẫn dùng được." }, { status: 503 });
    }
}
