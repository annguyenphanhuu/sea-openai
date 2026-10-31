import { test, expect, type Page } from "@playwright/test";
import type { Runtime } from "../src/lib/runtime";

function fixture(): Runtime {
    const orders: Runtime["orders"] = Array.from({ length: 30 }, (_, index) => ({
        order_id: `ORDER-${String(index).padStart(5, "0")}`, status: index === 0 ? "exception" : "late", guaranteed_date: "2026-10-22", revised_eta: "2026-10-25T02:46:00+07:00",
        late_days: 2, late_probability: 1, confidence: .82, fault_party: "carrier", reason_codes: ["guaranteed_day_exceeded", "linehaul_report_missing"], evidence: [], created_at: "2026-10-20T07:00:00+07:00", handed_over_at: null,
    }));
    return { mode: "local_integrated_web_inbox", llm: { enabled: true, model: "test-model" }, inside: { used_llm: true, codes: [] }, now: "2026-10-24T16:00:00+07:00", guard_alive: true, proactive_allowed: true, orders, orders_total: 6336, contact_queue_total: 255, phase_trace: ["A3", "A2", "A1"], feed_health: [{ feed: "orders", status: "trusted", source_timestamp: "2026-10-24T16:00:00+07:00" }], label_counts: { late: 100, exception: 12 }, selected_order_id: orders[0].order_id,
        chat: { session_id: "session-0", order_id: orders[0].order_id, status: "active", pending: null, messages: Array.from({ length: 40 }, (_, index) => ({ id: `message-${index}`, kind: index % 2 ? "response" : "customer", text: index === 39 ? "Phản hồi mới nhất đã xuất hiện." : `Nội dung trao đổi ${index}` })) },
        active_chats: Array.from({ length: 119 }, (_, index) => ({ session_id: `session-${index}`, order_id: `ORDER-${String(index).padStart(5, "0")}`, status: "active" })), ledger_total: 0, outbox_total: 0, handoffs: [], ledger: [], outbox: [], cancellations: [],
    };
}
async function mockRuntime(page: Page, value = fixture()) {
    await page.route("**/api/runtime**", async route => {
        const input = new URL(route.request().url()).searchParams;
        const orderId = input.get("order_id");
        if (orderId) {
            value.selected_order_id = orderId;
            if (value.chat) value.chat.order_id = orderId;
        }
        const sessionId = input.get("session_id");
        if (sessionId) {
            const session = value.active_chats.find(item => item.session_id === sessionId);
            if (session && value.chat) { value.chat.session_id = session.session_id; value.chat.order_id = session.order_id; value.selected_order_id = session.order_id; }
        }
        await route.fulfill({ json: value });
    });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Chăm sóc khách hàng", exact: true })).toBeVisible();
    await expect(page.locator("#customer-text")).toBeAttached();
}

test("care places composer above laptop fold and separates chat roles", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await mockRuntime(page);
    const send = page.getByRole("button", { name: "Gửi text", exact: true });
    const box = await send.boundingBox();
    expect(box).not.toBeNull();
    expect(box ? box.y + box.height : Infinity).toBeLessThanOrEqual(768);
    await expect(page.locator(".work-row")).toHaveCount(8);
    await expect(page.getByText("Phản hồi mới nhất đã xuất hiện.")).toBeVisible();
    expect(await page.locator(".conversation-messages").evaluate(element => element.scrollHeight - element.scrollTop - element.clientHeight)).toBeLessThan(3);
    const colors = await page.evaluate(() => [".message-customer", ".message-assistant"].map(selector => { const element = document.querySelector(selector); return element ? getComputedStyle(element).backgroundColor : null; }));
    expect(colors[0]).not.toBe(colors[1]);
    await expect(page.getByText("Bên được đánh giá có lỗi: Đơn vị vận chuyển.")).not.toBeVisible();
    await expect(page.getByText("linehaul_report_missing", { exact: false })).not.toBeVisible();
    await page.screenshot({ path: "test-results/polished-laptop.png", fullPage: true });
});

test("119 conversations use bounded searchable pages", async ({ page }) => {
    await mockRuntime(page);
    await page.getByRole("tab", { name: /Hội thoại/ }).click();
    await expect(page.locator(".session-row")).toHaveCount(8);
    await expect(page.getByText("1–8 / 119", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Trang sau" }).click();
    await expect(page.getByText("9–16 / 119", { exact: true })).toBeVisible();
    await page.getByRole("textbox", { name: "Tìm hội thoại" }).fill("00118");
    await expect(page.locator(".session-row")).toHaveCount(1);
    await expect(page.getByText("1–1 / 1", { exact: true })).toBeVisible();
    await expect(page.getByText("Đang trò chuyện", { exact: true })).toHaveCount(2);
});

test("navigation has distinct contents and localized logistics facts", async ({ page }) => {
    await mockRuntime(page);
    await page.getByRole("button", { name: /^Phòng điều hành/ }).click();
    await expect(page.getByRole("heading", { name: "Tổng quan vận hành", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Đơn cần chú ý", exact: true })).toBeVisible();
    await expect(page.locator(".chat-composer")).toHaveCount(0);
    await page.getByRole("button", { name: /^Phân tích logistics/ }).click();
    await expect(page.getByRole("heading", { name: "Đánh giá đơn hàng", exact: true })).toBeVisible();
    await expect(page.getByText("Bên được đánh giá có lỗi: Đơn vị vận chuyển.")).toBeVisible();
    await expect(page.getByText("Thiếu báo cáo tuyến vận chuyển để đối chiếu.")).toBeVisible();
    await expect(page.getByText("linehaul_report_missing", { exact: false })).not.toBeVisible();
    await page.getByText("Bằng chứng và chi tiết kỹ thuật", { exact: true }).click();
    await expect(page.getByText("linehaul_report_missing", { exact: false })).toBeVisible();
    await expect(page.getByText("Cam kết / Nguy cơ trễ", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: /^Giám sát dữ liệu/ }).click();
    await expect(page.getByRole("heading", { name: "Chất lượng nguồn dữ liệu", exact: true })).toBeVisible();
    await expect(page.getByText("Thông tin đơn hàng", { exact: true })).toBeVisible();
    await expect(page.locator(".chat-composer")).toHaveCount(0);
});

test("mobile detail opens directly and back preserves list search", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockRuntime(page);
    await expect(page.locator(".chat-composer")).not.toBeVisible();
    await page.getByRole("textbox", { name: "Tìm đơn hàng" }).fill("00001");
    await page.getByRole("button", { name: "Xem đơn ORDER-00001", exact: true }).click();
    await expect(page.locator(".chat-composer")).toBeVisible();
    await expect.poll(() => page.locator(".conversation-messages").evaluate(element => element.scrollHeight - element.scrollTop - element.clientHeight)).toBeLessThan(3);
    const box = await page.getByRole("button", { name: "Gửi text", exact: true }).boundingBox();
    expect(box ? box.y + box.height : Infinity).toBeLessThanOrEqual(844);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: "test-results/polished-mobile.png", fullPage: true });
    await page.getByRole("button", { name: "Danh sách", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "Tìm đơn hàng" })).toHaveValue("00001");
    await expect(page.locator(".work-row")).toHaveCount(1);
});

test("mismatched selected order cannot label another order chat", async ({ page }) => {
    const value = fixture();
    if (value.chat) value.chat.order_id = value.orders[1].order_id;
    await mockRuntime(page, value);
    await expect(page.locator(".conversation-heading h2")).toHaveText("ORDER-00001");
});

test("terminal session explains disabled composer", async ({ page }) => {
    const value = fixture();
    if (value.chat) value.chat.status = "transferred";
    await mockRuntime(page, value);
    await expect(page.getByRole("button", { name: "Gửi text", exact: true })).toBeDisabled();
    await expect(page.getByText("Đã chuyển nhân viên", { exact: true })).toBeVisible();
    await expect(page.getByText("Nhân viên tiếp nhận từ đây.", { exact: false })).toBeVisible();
});

test("dark theme keeps readable care layout", async ({ page }) => {
    await mockRuntime(page);
    await page.getByRole("button", { name: "Dùng giao diện tối" }).click();
    await expect(page.locator(".app-root")).toHaveAttribute("data-theme", "dark");
    await expect(page.locator(".chat-composer")).toBeVisible();
    await page.screenshot({ path: "test-results/polished-dark.png", fullPage: true });
});

test("initial render does not duplicate server-rendered control styles", async ({ page }) => {
    const duplicates: string[] = [];
    page.on("console", message => {
        if (message.text().includes("duplicate CSS rule")) duplicates.push(message.text());
    });
    await mockRuntime(page);
    expect(duplicates).toEqual([]);
});
