import { test, expect } from "@playwright/test";

test("search, filters, selection, evidence and preview actions", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/");
    await expect(page.getByRole("button", { name: /Xem đơn DEMO-0281/ })).toBeVisible();
    await page.screenshot({ path: "test-results/desktop-light.png", fullPage: true });
    await page.getByRole("textbox", { name: "Tìm đơn hàng" }).fill("không tồn tại");
    await expect(page.getByText("Không tìm thấy đơn phù hợp")).toBeVisible();
    await page.getByRole("button", { name: "Xóa bộ lọc" }).click();
    await page.getByRole("button", { name: /Cần chú ý/ }).click();
    await expect(page.getByRole("button", { name: /Xem đơn DEMO-/ })).toHaveCount(2);
    await page.getByRole("button", { name: "Tất cả", exact: true }).click();
    await page.getByRole("button", { name: /Xem đơn DEMO-0194/ }).click();
    await expect(page.getByRole("region", { name: "Hồ sơ DEMO-0194" })).toBeVisible();
    await page.getByRole("tab", { name: "Tổng quan" }).focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "Dòng thời gian" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("tabpanel")).toContainText("Đánh giá logistics");
    await page.getByRole("button", { name: "Chuẩn bị liên hệ", exact: true }).click();
    await expect(page.getByRole("tabpanel")).toContainText("Trần Hoàng Nam");
    await expect(page.getByRole("status")).toContainText(["Bản nháp đã sẵn sàng"]);
    await expect(page.getByRole("button", { name: "Đã chuẩn bị bản nháp" })).toBeDisabled();
    await page.getByRole("button", { name: "Chuyển nhân viên xem xét" }).click();
    await expect(page.getByRole("button", { name: "Đã xem trước chuyển người" })).toBeDisabled();
    await page.getByRole("button", { name: /Xem đơn DEMO-0342/ }).click();
    await expect(page.getByText("Chưa xác định", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Chuẩn bị liên hệ", exact: true })).toBeDisabled();
    await page.reload();
    await page.getByRole("button", { name: /Xem đơn DEMO-0194/ }).click();
    await page.getByRole("tab", { name: "Hội thoại" }).click();
    await expect(page.getByText("Chưa có bản nháp cho đơn này.")).toBeVisible();
    expect(errors).toEqual([]);
});

test("server rejects blocked demo drafts and malformed requests", async ({ request }) => {
    for (const input of [
        { orderId: "DEMO-0281", scenario: "failure", kind: "draft" },
        { orderId: "DEMO-0342", scenario: "healthy", kind: "draft" },
        { orderId: "DEMO-0408", scenario: "healthy", kind: "draft" },
    ]) {
        const response = await request.post("/api/demo/preview", { data: input });
        expect(response.status()).toBe(403);
    }
    expect((await request.post("/api/demo/preview", { data: { kind: "coins" } })).status()).toBe(400);
    expect((await request.post("/api/demo/preview", { data: { orderId: "missing", scenario: "healthy", kind: "handoff" } })).status()).toBe(404);
    const input = { orderId: "DEMO-0281", scenario: "healthy", kind: "draft" };
    const first = await request.post("/api/demo/preview", { data: input });
    const second = await request.post("/api/demo/preview", { data: input });
    expect(await first.json()).toEqual(await second.json());
    expect(await (await request.post("/api/demo/preview", { data: input })).json()).toMatchObject({ delivered: false, persisted: false });
});

test("guard failure blocks proactive contact in the UI", async ({ page }) => {
    await page.goto("/");
    await page.getByText("Điều khiển phiên minh họa").click();
    await page.getByRole("switch", { name: "Mô phỏng sự cố nguồn dữ liệu" }).check();
    await expect(page.getByText("A3 đang chặn liên hệ chủ động")).toBeVisible();
    await expect(page.getByRole("button", { name: "Chuẩn bị liên hệ", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Chuyển nhân viên xem xét" })).toBeEnabled();
    await page.getByRole("button", { name: "Xem giám sát" }).click();
    await expect(page.getByRole("heading", { name: "Điều kiện liên hệ chủ động" })).toBeVisible();
});

test("loading and recoverable transport errors", async ({ page }) => {
    await page.route("**/api/demo/snapshot?*", async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 400));
        await route.fulfill({ status: 503, json: { error: "Nguồn demo tạm thời không khả dụng." } });
    });
    await page.goto("/");
    await expect(page.getByLabel("Đang tải phòng điều hành")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Chưa thể tải phòng điều hành" })).toBeVisible();
    await page.unroute("**/api/demo/snapshot?*");
    await page.getByRole("button", { name: "Thử lại" }).click();
    await expect(page.getByRole("button", { name: /Xem đơn DEMO-0281/ })).toBeVisible();
});

for (const scheme of ["light", "dark"] satisfies ("light" | "dark")[]) {
    test(`responsive layouts and theme: ${scheme}`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
        await page.goto("/");
        await expect(page.getByRole("button", { name: /Xem đơn DEMO-0281/ })).toBeVisible();
        await expect(page.locator("[data-theme]")).toHaveAttribute("data-theme", scheme);
        await page.screenshot({ path: `test-results/desktop-${scheme}.png`, fullPage: true });
        for (const width of [375, 768, 1024, 1440]) {
            await page.setViewportSize({ width, height: 900 });
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        }
        await page.setViewportSize({ width: 375, height: 850 });
        await page.screenshot({ path: `test-results/mobile-${scheme}.png`, fullPage: true });
        await page.getByRole("button", { name: "Mở menu" }).click();
        await expect(page.getByRole("button", { name: "Đóng menu" })).toBeFocused();
        await page.keyboard.press("Escape");
        await expect(page.getByRole("button", { name: "Mở menu" })).toBeFocused();
        await page.getByRole("button", { name: "Mở menu" }).click();
        await page.getByRole("button", { name: /Chăm sóc khách hàng/ }).click();
        await expect(page.getByRole("heading", { name: "Chăm sóc từ những điều đã biết." })).toBeVisible();
        await expect(page.getByRole("button", { name: "Đóng menu" })).toBeHidden();
        await page.getByRole("button", { name: scheme === "light" ? "Dùng giao diện tối" : "Dùng giao diện sáng" }).click();
        await expect(page.locator("[data-theme]")).toHaveAttribute("data-theme", scheme === "light" ? "dark" : "light");
        await page.reload();
        await expect(page.locator("[data-theme]")).toHaveAttribute("data-theme", scheme === "light" ? "dark" : "light");
    });
}
