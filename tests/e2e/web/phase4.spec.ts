import { expect, test, type Page } from "@playwright/test";

// Chạy trên stack thật sau khi đã có dự án DEMO (seed-demo) và ít nhất một lần chạy đã kết thúc.
const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "";
const DEMO_URL = process.env.E2E_DEMO_URL ?? "http://127.0.0.1:8100";
const shots = "../../artifacts/e2e/screenshots";

test.skip(!EMAIL || !PASSWORD, "Cần E2E_ADMIN_EMAIL và E2E_ADMIN_PASSWORD");

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Mật khẩu").fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByRole("heading", { name: "Cổng kiểm thử tự động OmniTest" })).toBeVisible();
}

async function expectNoHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.visualViewport!.width + 1)).toBe(true);
}

async function openDemoProject(page: Page, path: string) {
  await page.goto(path);
  const picker = page.getByLabel("Dự án");
  const demo = await picker.locator("option", { hasText: "DEMO ·" }).getAttribute("value");
  expect(demo, "Chưa có dự án DEMO, hãy chạy lệnh seed-demo").toBeTruthy();
  await picker.selectOption(demo as string);
}

test("báo cáo dự án: số liệu, bộ lọc, xuất Excel và HTML", async ({ page }, info) => {
  await login(page);
  await openDemoProject(page, "/reports");
  await expect(page.getByRole("heading", { name: "Báo cáo" })).toBeVisible();
  await expect(page.getByText("Tỷ lệ đạt").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Theo môi trường" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Theo test case" })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: `${shots}/${info.project.name}-reports.png`, fullPage: true });

  // Số lần chạy trên giao diện khớp API (cùng bộ lọc mặc định).
  const projectId = new URL(page.url()).searchParams.get("project");
  const api = await (await page.request.get(`/api/projects/${projectId}/reports/summary`)).json();
  await expect(page.getByText(String(api.runs), { exact: true }).first()).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Excel" }).click();
  expect((await download).suggestedFilename()).toMatch(/^DEMO-bao-cao-\d{8}-\d{8}\.xlsx$/);

  const href = await page.getByRole("link", { name: "HTML" }).getAttribute("href");
  const html = await page.request.get(href as string);
  expect(html.headers()["content-security-policy"]).toContain("sandbox");
  expect(await html.text()).toContain("Báo cáo kiểm thử dự án DEMO");

  // Lọc khoảng ngày tương lai: trạng thái rỗng, không hiện 0% giả.
  await page.getByLabel("Từ ngày").fill("2099-01-01");
  await page.getByLabel("Đến ngày").fill("2099-01-02");
  await expect(page.getByText("Chưa có lần chạy nào trong khoảng này")).toBeVisible();
});

test("chi tiết lần chạy có nút xuất báo cáo", async ({ page }) => {
  await login(page);
  await openDemoProject(page, "/test-runs");
  const first = page.locator("tbody a").first();
  await first.click();
  await expect(page).toHaveURL(/\/test-runs\/[0-9a-f-]+$/);
  const link = page.getByRole("link", { name: "Báo cáo HTML" });
  await expect(link).toBeVisible();
  const res = await page.request.get((await link.getAttribute("href")) as string);
  expect(res.status()).toBe(200);
  expect(await res.text()).toContain("Báo cáo lần chạy");
  await expect(page.getByRole("link", { name: "Excel" })).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test("xem trước import OpenAPI của ứng dụng demo", async ({ page }, info) => {
  await login(page);
  await openDemoProject(page, "/test-cases");
  const spec = await (await page.request.get(`${DEMO_URL}/openapi.json`)).body();
  await page.getByRole("button", { name: "Từ OpenAPI" }).click();
  const dlg = page.getByRole("dialog");
  await dlg.getByLabel(/Tài liệu OpenAPI/).setInputFiles({ name: "demo-openapi.json", mimeType: "application/json", buffer: spec });
  await dlg.getByRole("button", { name: "Xem trước" }).click();
  await expect(dlg.getByRole("status")).toContainText("operation");
  await expect(dlg.getByText("/api/items/{item_id}").first()).toBeVisible();
  await expect(dlg.getByText("thay đổi dữ liệu").first()).toBeVisible();
  await expect(dlg.getByText("cần biến: TO")).toBeVisible();
  await page.screenshot({ path: `${shots}/${info.project.name}-openapi-preview.png` });
  await expectNoHorizontalOverflow(page);
  // Chỉ xem trước, không tạo dữ liệu trong dự án demo.
  await dlg.getByRole("button", { name: "Hủy" }).click();
  await expect(dlg).toBeHidden();
});
