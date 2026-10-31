import { defineConfig } from "@playwright/test";

export default defineConfig({
    testDir: "./tests", fullyParallel: false, workers: 1,
    use: { baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000", channel: process.env.PLAYWRIGHT_CHANNEL || undefined, viewport: { width: 1440, height: 1000 }, trace: "retain-on-failure" },
    webServer: { command: "npm run start", url: process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000", reuseExistingServer: !process.env.CI, timeout: 60000 },
});
