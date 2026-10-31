import { test, expect } from "@playwright/test";
import type { Runtime } from "../src/lib/runtime";

function runtime(): Runtime {
    return { mode: "local_integrated_web_inbox", now: "2026-10-24T16:00:00+07:00", guard_alive: true, proactive_allowed: true,
        orders: [{ order_id: "voice-order", status: "late", guaranteed_date: "2026-10-22", revised_eta: null, late_days: 2, late_probability: 1, confidence: .8, fault_party: "carrier", reason_codes: [], evidence: [] }],
        orders_total: 1, contact_queue_total: 1, phase_trace: ["A3", "A2", "A1"], feed_health: [], label_counts: { late: 1 }, selected_order_id: "voice-order",
        chat: { session_id: "text-parent", order_id: "voice-order", status: "active", pending: null, messages: [] }, active_chats: [{ session_id: "text-parent", order_id: "voice-order", status: "active" }], ledger_total: 0, outbox_total: 0, handoffs: [], ledger: [], outbox: [], cancellations: [] };
}
async function pageRuntime(page: import("@playwright/test").Page) {
    await page.route("**/api/runtime**", route => route.fulfill({ json: runtime() }));
}

async function fakeAudioTransport(page: import("@playwright/test").Page) {
    await page.addInitScript(() => {
        let stops = 0; let closes = 0; const sent: string[] = [];
        Object.defineProperty(window, "voiceSent", { get: () => sent });
        Object.defineProperty(window, "voiceResources", { get: () => ({ stops, closes }) });
        const track = { enabled: true, stop: () => { stops++; } };
        Object.defineProperty(navigator.mediaDevices, "getUserMedia", { value: async () => ({ getTracks: () => [track], getAudioTracks: () => [track] }) });
        class Peer {
            connectionState = "connected";
            ontrack: ((event: { streams: MediaStream[]; track: { stop: () => void } }) => void) | null = null;
            onconnectionstatechange = null;
            channel: { readyState: string; onopen: (() => void) | null; onmessage: ((event: { data: string }) => void) | null; send: (data: string) => void; close: () => void } = { readyState: "open", onopen: null, onmessage: null, send: (data: string) => { sent.push(data); }, close: () => { closes++; } };
            createDataChannel() { window.addEventListener("voice-track", () => this.ontrack?.({ streams: [new MediaStream()], track: { stop: () => { stops++; } } })); window.addEventListener("voice-tool", event => { if (event instanceof CustomEvent) this.channel.onmessage?.({ data: JSON.stringify(event.detail) }); }); return this.channel; }
            addTrack() {}
            async createOffer() { return { type: "offer", sdp: "fake-offer" }; }
            async setLocalDescription() {}
            async setRemoteDescription() { this.channel.onopen?.(); }
            close() { closes++; }
        }
        Object.defineProperty(window, "RTCPeerConnection", { value: Peer });
    });
}

test("voice microphone denial is explicit and does not issue a credential", async ({ page }) => {
    await pageRuntime(page);
    let issued = 0;
    await page.route("**/api/voice/**", async route => {
        if (route.request().url().endsWith("/create")) issued++;
        await route.fulfill({ json: { available: true, max_duration_seconds: 240, budget_remaining_usd: 2 } });
    });
    await page.addInitScript(() => Object.defineProperty(navigator.mediaDevices, "getUserMedia", { value: async () => { throw new DOMException("Denied", "NotAllowedError"); } }));
    await page.goto("/");
    await page.getByRole("button", { name: "Nói chuyện với AI", exact: true }).click();
    await expect(page.getByText("Bạn chưa cho phép dùng microphone. Chat text vẫn dùng được.", { exact: true })).toBeVisible();
    expect(issued).toBe(0);
    await expect(page.getByRole("button", { name: "Nói chuyện với AI", exact: true })).toBeEnabled();
});

test("voice tool uses server voice channel once and stop releases media", async ({ page }) => {
    await pageRuntime(page);
    const turns: unknown[] = [];
    let ended = 0;
    await page.route("**/api/voice/**", async route => {
        const operation = route.request().url().split("/").pop();
        if (operation === "state") return route.fulfill({ json: { available: true, max_duration_seconds: 240, budget_remaining_usd: 2 } });
        if (operation === "create") return route.fulfill({ json: { voice_session_id: "voice-token", care_session_id: "web-voice-child", client_secret: "ek_test", expires_at: Date.now()/1000 + 60, deadline_at: Date.now()/1000 + 120, max_duration_seconds: 120 } });
        if (operation === "turn") { turns.push(route.request().postDataJSON()); return route.fulfill({ json: { reply: "Xin chào bạn.", inside: { channel: "voice", codes: [] }, status: "active" } }); }
        ended++;
        return route.fulfill({ json: { budget_remaining_usd: 1.5, status: "ended", provider_billing_cap: false } });
    });
    await page.route("https://api.openai.com/v1/realtime/calls", route => route.fulfill({ body: "fake-answer" }));
    await fakeAudioTransport(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Nói chuyện với AI", exact: true }).click();
    await expect(page.getByText("Đã kết nối. Bạn có thể nói.", { exact: true })).toBeVisible();
    await page.evaluate(() => window.dispatchEvent(new CustomEvent("voice-tool", { detail: { type: "input_audio_buffer.committed" } })));
    const requests: string[] = await page.evaluate(() => Reflect.get(window, "voiceSent"));
    expect(requests.map(value => JSON.parse(value))).toContainEqual({ type: "response.create", response: { tool_choice: "required" } });
    const event = { type: "response.done", response: { status: "completed", output: [{ type: "function_call", name: "send_to_a1", call_id: "call-one", arguments: JSON.stringify({ text: "Xin chào" }) }] } };
    await page.evaluate(event => { window.dispatchEvent(new CustomEvent("voice-tool", { detail: event })); window.dispatchEvent(new CustomEvent("voice-tool", { detail: event })); }, event);
    await expect.poll(() => turns.length).toBe(1);
    expect(turns[0]).toMatchObject({ session_id: "web-voice-child", voice_session_id: "voice-token", text: "Xin chào", request_id: "voice:voice-token:call-one" });
    await page.getByRole("button", { name: "Kết thúc voice", exact: true }).click();
    await expect.poll(() => ended).toBe(1);
    const resources = await page.evaluate(() => Reflect.get(window, "voiceResources"));
    expect(resources.stops).toBe(1);
    expect(resources.closes).toBeGreaterThanOrEqual(2);
    await expect(page.getByRole("button", { name: "Nói chuyện với AI", exact: true })).toBeEnabled();
});


test("stopping before microphone permission resolves releases late tracks", async ({ page }) => {
    await pageRuntime(page);
    let issued = 0;
    await page.route("**/api/voice/**", async route => {
        if (route.request().url().endsWith("/create")) issued++;
        await route.fulfill({ json: { available: true, max_duration_seconds: 240, budget_remaining_usd: 2 } });
    });
    await page.addInitScript(() => {
        let stops = 0;
        Object.defineProperty(window, "lateStops", { get: () => stops });
        Object.defineProperty(navigator.mediaDevices, "getUserMedia", { value: () => new Promise(resolve => {
            window.addEventListener("allow-late-microphone", () => resolve({ getTracks: () => [{ stop: () => { stops++; } }] }), { once: true });
        }) });
    });
    await page.goto("/");
    await page.getByRole("button", { name: "Nói chuyện với AI", exact: true }).click();
    await page.getByRole("button", { name: "Kết thúc voice", exact: true }).click();
    await page.evaluate(() => window.dispatchEvent(new Event("allow-late-microphone")));
    await expect.poll(() => page.evaluate(() => Reflect.get(window, "lateStops"))).toBe(1);
    expect(issued).toBe(0);
});

test("provider failure releases microphone and returns to text", async ({ page }) => {
    await pageRuntime(page);
    await fakeAudioTransport(page);
    await page.route("**/api/voice/**", async route => {
        if (route.request().url().endsWith("/state")) return route.fulfill({ json: { available: true, max_duration_seconds: 240, budget_remaining_usd: 2 } });
        return route.fulfill({ status: 503, json: { error: "Provider unavailable" } });
    });
    await page.goto("/");
    await page.getByRole("button", { name: "Nói chuyện với AI", exact: true }).click();
    await expect(page.getByText("Provider unavailable", { exact: true })).toBeVisible();
    expect((await page.evaluate(() => Reflect.get(window, "voiceResources"))).stops).toBe(1);
    await expect(page.getByRole("textbox", { name: "Tin nhắn khách trong phiên local" })).toBeEnabled();
});

test("leaving the conversation stops tracks and ends the voice session", async ({ page }) => {
    await pageRuntime(page);
    await fakeAudioTransport(page);
    let ended = 0;
    await page.route("**/api/voice/**", async route => {
        const operation = route.request().url().split("/").pop();
        if (operation === "state") return route.fulfill({ json: { available: true, max_duration_seconds: 240, budget_remaining_usd: 2 } });
        if (operation === "create") return route.fulfill({ json: { voice_session_id: "voice-token", care_session_id: "web-voice-child", client_secret: "ek_test", expires_at: Date.now()/1000 + 60, deadline_at: Date.now()/1000 + 120, max_duration_seconds: 120 } });
        ended++;
        return route.fulfill({ json: { budget_remaining_usd: 1.5, status: "ended", provider_billing_cap: false } });
    });
    await page.route("https://api.openai.com/v1/realtime/calls", route => route.fulfill({ body: "fake-answer" }));
    await page.goto("/");
    await page.getByRole("button", { name: "Nói chuyện với AI", exact: true }).click();
    await expect(page.getByText("Đã kết nối. Bạn có thể nói.", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: /^Phân tích logistics/ }).click();
    await expect.poll(() => ended).toBe(1);
    const resources = await page.evaluate(() => Reflect.get(window, "voiceResources"));
    expect(resources.stops).toBe(1);
    expect(resources.closes).toBeGreaterThanOrEqual(2);
});


test("late playback failure after stop cannot reactivate voice", async ({ page }) => {
    await pageRuntime(page);
    await fakeAudioTransport(page);
    await page.addInitScript(() => Object.defineProperty(HTMLMediaElement.prototype, "play", { value: () => new Promise((resolve, reject) => {
        window.addEventListener("reject-playback", () => reject(new DOMException("Blocked", "NotAllowedError")), { once: true });
    }) }));
    await page.route("**/api/voice/**", async route => {
        const operation = route.request().url().split("/").pop();
        if (operation === "state") return route.fulfill({ json: { available: true, max_duration_seconds: 240, budget_remaining_usd: 2 } });
        if (operation === "create") return route.fulfill({ json: { voice_session_id: "voice-token", care_session_id: "web-voice-child", client_secret: "ek_test", expires_at: Date.now()/1000 + 60, deadline_at: Date.now()/1000 + 120, max_duration_seconds: 120 } });
        return route.fulfill({ json: { budget_remaining_usd: 1.5, status: "ended", provider_billing_cap: false } });
    });
    await page.route("https://api.openai.com/v1/realtime/calls", route => route.fulfill({ body: "fake-answer" }));
    await page.goto("/");
    await page.getByRole("button", { name: "Nói chuyện với AI", exact: true }).click();
    await expect(page.getByText("Đã kết nối. Bạn có thể nói.", { exact: true })).toBeVisible();
    await page.evaluate(() => window.dispatchEvent(new Event("voice-track")));
    await page.getByRole("button", { name: "Kết thúc voice", exact: true }).click();
    await expect(page.getByRole("button", { name: "Nói chuyện với AI", exact: true })).toBeEnabled();
    await page.evaluate(() => { window.dispatchEvent(new Event("reject-playback")); window.dispatchEvent(new Event("voice-track")); });
    await expect(page.getByRole("button", { name: "Kết thúc voice", exact: true })).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: "Tin nhắn khách trong phiên local" })).toBeEnabled();
    expect(await page.locator('audio').evaluate(audio => audio instanceof HTMLMediaElement ? audio.srcObject : null)).toBeNull();
});
