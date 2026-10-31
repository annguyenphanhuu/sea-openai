import { z } from "zod";
import { previewSchema, snapshotSchema, type Scenario } from "./demo";

async function readResponse<T>(response: Response, schema: z.ZodType<T>): Promise<T> {
    if (!response.ok) {
        const error: unknown = await response.json().catch(() => null);
        const parsed = z.object({ error: z.string() }).safeParse(error);
        throw new Error(parsed.success ? parsed.data.error : "Không thể tải dữ liệu. Vui lòng thử lại.");
    }
    const parsed = schema.safeParse(await response.json());
    if (!parsed.success) throw new Error("Dữ liệu trả về chưa đúng định dạng. Vui lòng thử lại.");
    return parsed.data;
}
export async function loadSnapshot(scenario: Scenario, signal?: AbortSignal) {
    return readResponse(await fetch(`/api/demo/snapshot?scenario=${scenario}`, { cache: "no-store", signal }), snapshotSchema);
}
export async function requestPreview(input: { orderId: string; scenario: Scenario; kind: "draft" | "handoff" }, signal?: AbortSignal) {
    return readResponse(await fetch("/api/demo/preview", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input), signal,
    }), previewSchema);
}
