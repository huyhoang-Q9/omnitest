import { defineConfig, devices } from "@playwright/test";

// E2E chạy trên stack thật (API + DB + web). Khởi động trước bằng infra/scripts/dev.sh.
export default defineConfig({
  testDir: "../../tests/e2e/web",
  outputDir: "../../artifacts/e2e/results",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { outputFolder: "../../artifacts/e2e/report", open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "vi-VN",
    // Cho phép dùng Chromium có sẵn trên máy khi phiên bản Playwright khác bản trình duyệt đã cài.
    launchOptions: process.env.PW_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PW_CHROMIUM_EXECUTABLE }
      : undefined,
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
