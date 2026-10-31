import { test, expect } from "@playwright/test";

test("real pipeline, persisted chat, guard and handoff", async ({ page, request }) => {
    test.setTimeout(120000);
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Phòng điều hành tích hợp." })).toBeVisible();
    await expect(page.getByText("Đang kết nối pipeline...")).toHaveCount(0);
    const snapshot = await request.get("/api/runtime");
    expect(snapshot.ok()).toBeTruthy();
    const state = await snapshot.json();
    if (!state.orders_total) {
        await page.getByRole("button", { name: "NEXT +30 phút" }).click();
    }
    await expect(page.getByRole("button", { name: "Xem đơn 261021ZS7E76FW", exact: true })).toBeVisible({ timeout: 60000 });
    await page.getByRole("button", { name: "Xem đơn 261021ZS7E76FW", exact: true }).click();
    await expect(page.getByText("Tin nhắn khách trong phiên local")).toBeVisible();
    await page.getByRole("textbox", { name: "Tin nhắn khách trong phiên local" }).fill("Tại sao đơn hàng trễ?");
    await page.getByRole("button", { name: "Gửi text", exact: true }).click();
    await expect(page.getByText("Tại sao đơn hàng trễ?", { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByText("Tại sao đơn hàng trễ?", { exact: true })).toBeVisible();
    await page.getByRole("textbox", { name: "Tin nhắn khách trong phiên local" }).fill("Tôi muốn hủy đơn");
    await page.getByRole("button", { name: "Gửi text", exact: true }).click();
    await expect(page.getByRole("button", { name: "Xác nhận yêu cầu hủy" })).toBeVisible();
    const beforeConfirm = await (await request.get("/api/runtime")).json();
    expect(beforeConfirm.cancellations).toHaveLength(0);
    await page.getByRole("button", { name: "Xác nhận yêu cầu hủy" }).click();
    await expect.poll(async () => (await (await request.get("/api/runtime")).json()).cancellations.length).toBeGreaterThan(0);
    await page.getByRole("button", { name: "Giám sát dữ liệu" }).click();
    await page.getByRole("button", { name: "Dừng A3", exact: true }).click();
    await expect(page.getByText("A3 đang chặn liên hệ chủ động", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Chăm sóc khách hàng" }).click();
    await page.getByRole("button", { name: "Yêu cầu gặp nhân viên" }).click();
    await expect(page.getByRole("button", { name: "Gửi text", exact: true })).toBeDisabled();
    await expect(page.getByText("Đang xử lý...", { exact: true })).toHaveCount(0);
    await page.screenshot({ path: "test-results/integrated-runtime.png", fullPage: true });
    const after = await (await request.get("/api/runtime")).json();
    expect(after.handoffs.length).toBeGreaterThan(0);
    expect(after.phase_trace).toEqual(["A3", "A2", "A1"]);
    expect(errors).toEqual([]);
});

test("proxy rejects cross-origin, public host and invalid commands", async ({ request, baseURL }) => {
    expect((await request.post("/api/runtime", { data: { kind: "kill" }, headers: { Origin: "https://example.com" } })).status()).toBe(403);
    expect((await request.get("/api/runtime", { headers: { "X-Forwarded-Host": "example.com" } })).status()).toBe(403);
    expect((await request.post("/api/runtime", { data: { kind: "pay", amount: 1000 }, headers: { Origin: baseURL || "http://127.0.0.1:3000" } })).status()).toBe(400);
});
