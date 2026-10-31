import { test, expect } from "@playwright/test";
import { readChatStream, type Runtime, type SayCommand } from "../src/lib/runtime";

function snapshot(): Runtime {
    return { mode: "local_integrated_web_inbox", now: "2026-10-24T16:00:00+07:00", guard_alive: true, proactive_allowed: true,
        orders: [{ order_id: "order-stream", status: "late", guaranteed_date: "2026-10-22", revised_eta: null, late_days: 2, late_probability: 1, confidence: .8, fault_party: "carrier", reason_codes: [], evidence: [] }],
        orders_total: 1, contact_queue_total: 1, phase_trace: ["A3", "A2", "A1"], feed_health: [], label_counts: { late: 1 }, selected_order_id: "order-stream",
        chat: { session_id: "session-stream", order_id: "order-stream", status: "active", pending: null, messages: [] },
        active_chats: [{ session_id: "session-stream", order_id: "order-stream", status: "active" }], ledger_total: 0, outbox_total: 0, handoffs: [], ledger: [], outbox: [], cancellations: [] };
}
const command: SayCommand = { kind: "say", session_id: "session-stream", request_id: "a8b1430f-b621-4ab8-a434-139122a83ca8", text: "Xin chào" };
function response(events: object[]) {
    const bytes = new TextEncoder().encode(events.map(event => JSON.stringify(event) + "\n").join(""));
    return new Response(new ReadableStream<Uint8Array>({ start(controller) { for (const byte of bytes) controller.enqueue(Uint8Array.of(byte)); controller.close(); } }), { headers: { "Content-Type": "application/x-ndjson" } });
}

test("chat stream parses fragmented UTF-8 frames and requires committed completion", async () => {
    const seen: string[] = [];
    const value = await readChatStream(response([
        { kind: "acknowledged", request_id: command.request_id },
        { kind: "status", request_id: command.request_id, status: "processing" },
        { kind: "reply", request_id: command.request_id, message_id: "reply", text: "Chào bạn nhé 👋" },
        { kind: "done", request_id: command.request_id, snapshot: snapshot() },
    ]), command, event => seen.push(event.kind === "reply" ? event.text : event.kind));
    expect(value.chat?.session_id).toBe(command.session_id);
    expect(seen).toEqual(["acknowledged", "status", "Chào bạn nhé 👋", "done"]);
    await expect(readChatStream(response([{ kind: "acknowledged", request_id: command.request_id }]), command, () => {})).rejects.toThrow("ngắt");
});

test("chat stream rejects wrong identity, stream errors and data after completion", async () => {
    await expect(readChatStream(response([{ kind: "acknowledged", request_id: "other" }]), command, () => {})).rejects.toThrow("khớp");
    await expect(readChatStream(response([{ kind: "error", request_id: command.request_id, message: "Retry same key" }]), command, () => {})).rejects.toThrow("Retry same key");
    const wrong = snapshot();
    if (wrong.chat) wrong.chat.session_id = "different";
    await expect(readChatStream(response([{ kind: "done", request_id: command.request_id, snapshot: wrong }]), command, () => {})).rejects.toThrow("khớp");
    await expect(readChatStream(Response.json(wrong), command, () => {})).rejects.toThrow("khớp");
    await expect(readChatStream(response([{ kind: "done", request_id: command.request_id, snapshot: snapshot() }, { kind: "acknowledged", request_id: command.request_id }]), command, () => {})).rejects.toThrow("hoàn tất");
});

test("customer message appears before a held reply and reconciles without duplication", async ({ page }) => {
    const value = snapshot();
    let release = () => {};
    const held = new Promise<void>(resolve => { release = resolve; });
    await page.route("**/api/runtime**", async route => {
        if (route.request().method() === "POST") {
            await held;
            if (value.chat) value.chat.messages = [{ id: "customer", kind: "customer", text: "Xin chào" }, { id: "response", kind: "response", text: "Chào bạn!" }];
        }
        await route.fulfill({ json: value });
    });
    await page.goto("/");
    const input = page.getByRole("textbox", { name: "Tin nhắn khách trong phiên local" });
    await input.fill("Xin chào");
    await input.press("Enter");
    await expect(page.locator(".message-customer p")).toHaveText("Xin chào");
    await expect(page.locator(".message-customer p")).toBeVisible();
    await expect(input).toHaveValue("");
    await expect(page.getByText("A1 đang xử lý và kiểm tra câu trả lời…", { exact: true })).toBeVisible();
    await expect(page.getByText("Chào bạn!", { exact: true })).toHaveCount(0);
    release();
    await expect(page.getByText("Chào bạn!", { exact: true })).toBeVisible();
    await expect(page.locator(".message-customer")).toHaveCount(1);
    await expect(page.locator("[data-delivery]")).toHaveCount(0);
});

test("uncertain delivery survives reload and retries the same request ID", async ({ page }) => {
    const value = snapshot();
    const requests: string[] = [];
    await page.route("**/api/runtime**", async route => {
        if (route.request().method() === "POST") {
            const body = route.request().postDataJSON();
            requests.push(body.request_id);
            if (requests.length === 1) { await route.fulfill({ status: 503, json: { error: "Uncertain" } }); return; }
            if (value.chat) value.chat.messages = [{ id: "customer", kind: "customer", text: "Xin chào" }, { id: "response", kind: "response", text: "Đã nhận câu hỏi." }];
        }
        await route.fulfill({ json: value });
    });
    await page.goto("/");
    await page.getByRole("textbox", { name: "Tin nhắn khách trong phiên local" }).fill("Xin chào");
    await page.getByRole("button", { name: "Gửi text", exact: true }).click();
    await expect(page.getByRole("button", { name: "Gửi lại cùng yêu cầu" })).toBeVisible();
    await page.reload();
    await page.getByRole("button", { name: "Gửi lại cùng yêu cầu" }).click();
    await expect(page.getByText("Đã nhận câu hỏi.", { exact: true })).toBeVisible();
    expect(requests).toHaveLength(2);
    expect(requests[1]).toBe(requests[0]);
    await expect(page.locator(".message-customer")).toHaveCount(1);
    expect(await page.evaluate(() => sessionStorage.getItem("cho-pho-pending-turn"))).toBeNull();
});

test("cached uncertain request can recover from a failed initial snapshot", async ({ page }) => {
    await page.addInitScript(command => sessionStorage.setItem("cho-pho-pending-turn", JSON.stringify(command)), command);
    let recovering = false;
    const sent: string[] = [];
    const value = snapshot();
    await page.route("**/api/runtime**", async route => {
        if (route.request().method() === "GET") {
            if (!recovering) { await route.fulfill({ status: 503, json: { error: "Unavailable" } }); return; }
            expect(new URL(route.request().url()).searchParams.get("session_id")).toBe(command.session_id);
        } else {
            sent.push(route.request().postDataJSON().request_id);
            if (value.chat) value.chat.messages = [{ id: "response", kind: "response", text: "Đã đối soát yêu cầu." }];
        }
        await route.fulfill({ json: value });
    });
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Thử lại", exact: true })).toBeVisible();
    recovering = true;
    await page.getByRole("button", { name: "Thử lại", exact: true }).click();
    await page.getByRole("button", { name: "Gửi lại cùng yêu cầu" }).click();
    await expect(page.getByText("Đã đối soát yêu cầu.", { exact: true })).toBeVisible();
    expect(sent).toEqual([command.request_id]);
});

test("storage cleanup failure cannot turn a committed reply into uncertain delivery", async ({ page }) => {
    await page.addInitScript(() => { Storage.prototype.removeItem = () => { throw new DOMException("Blocked", "SecurityError"); }; });
    const value = snapshot();
    const sent: string[] = [];
    await page.route("**/api/runtime**", async route => {
        if (route.request().method() === "POST") {
            sent.push(route.request().postDataJSON().request_id);
            if (value.chat) value.chat.messages = [{ id: "reply", kind: "response", text: "Phản hồi đã lưu." }];
        }
        await route.fulfill({ json: value });
    });
    await page.goto("/");
    const input = page.getByRole("textbox", { name: "Tin nhắn khách trong phiên local" });
    await input.fill("Xin chào");
    await input.press("Enter");
    await expect(page.getByText("Phản hồi đã lưu.", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Gửi lại cùng yêu cầu" })).toHaveCount(0);
    await expect(input).toBeEnabled();
    expect(sent).toHaveLength(1);
});
