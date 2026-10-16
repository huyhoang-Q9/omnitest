import { expect, test, type Page } from "@playwright/test";

// Portal kiểm thử trên stack thật (API + worker + demo-target), cần đã chạy seed-demo cho E2E_ADMIN_EMAIL.
const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "";
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

test("trang chủ portal: hành động chính, hệ thống, lần chạy gần đây", async ({ page }, info) => {
  await login(page);
  await expect(page.getByRole("heading", { name: "Bạn muốn làm gì?" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Kiểm tra nhanh/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hệ thống của bạn" })).toBeVisible();
  await expect(page.getByRole("link", { name: /^Kiểm thử .* của DEMO$/ }).first()).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: `${shots}/${info.project.name}-portal-home.png`, fullPage: true });
});

test("kiểm thử hệ thống 3 bước: kiểm tra nhanh chạy thật qua worker", async ({ page }, info) => {
  test.setTimeout(120_000);
  await login(page);
  await page.getByRole("link", { name: /^Kiểm thử .* của DEMO$/ }).first().click();
  await expect(page.getByRole("heading", { name: "Kiểm thử hệ thống" })).toBeVisible();
  const project = page.getByLabel("Dự án", { exact: true });
  expect(await project.evaluate((el: HTMLSelectElement) => el.selectedOptions[0]?.text)).toMatch(/^DEMO ·/);

  await page.getByText("Kiểm tra nhanh", { exact: true }).click();
  const create = page.getByRole("button", { name: "Tạo bộ kiểm tra nhanh" });
  if (await create.isVisible()) await create.click();
  await expect(page.getByText("Kiểm tra nhanh (2 test)")).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: `${shots}/${info.project.name}-portal-wizard.png`, fullPage: true });

  await page.getByRole("button", { name: "Bắt đầu kiểm thử" }).click();
  await expect(page).toHaveURL(/\/test-runs\/[0-9a-f-]+$/);
  // Kết quả do worker chạy thật trên demo-target; chờ tới khi xong.
  await expect(page.getByText("2/2 xong")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText("2 đạt")).toBeVisible();
  await page.getByRole("button", { name: /Kiểm tra nhanh: trang web mở được/ }).click();
  await page.getByRole("button", { name: /Chụp màn hình/ }).click();
  const img = page.getByRole("img", { name: /Ảnh chụp/ });
  await expect(img).toBeVisible();
  expect(await img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(100);
  await page.screenshot({ path: `${shots}/${info.project.name}-portal-result.png`, fullPage: true });
});

test("hướng dẫn sử dụng: ảnh màn hình thật, mở đúng màn hình, đánh dấu đã làm", async ({ page }, info) => {
  await login(page);
  await page.getByRole("link", { name: "Hướng dẫn sử dụng" }).first().click();
  await expect(page.getByRole("heading", { name: "Hướng dẫn sử dụng OmniTest" })).toBeVisible();
  const img = page.getByRole("img", { name: "Màn hình: Kiểm thử một hệ thống trong 3 bước" });
  await img.scrollIntoViewIfNeeded();
  await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(100);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: `${shots}/${info.project.name}-guide.png` });

  const section = page.locator("#kiem-thu");
  await section.getByRole("button", { name: "Đánh dấu đã làm" }).click();
  await expect(section.getByRole("button", { name: "Đã làm" })).toBeVisible();
  await page.reload();
  await expect(page.locator("#kiem-thu").getByRole("button", { name: "Đã làm" })).toBeVisible();
  await page.locator("#kiem-thu").getByRole("button", { name: "Đã làm" }).click();

  await page.locator("#kiem-thu").getByRole("link", { name: "Mở màn hình này" }).click();
  await expect(page).toHaveURL(/\/test$/);
  await expect(page.getByRole("heading", { name: "Kiểm thử hệ thống" })).toBeVisible();
});

test("soạn test case từ trang chủ: chọn dự án trước", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: /Soạn test case/ }).click();
  await expect(page.getByRole("heading", { name: "Tạo test case" })).toBeVisible();
  await page.getByRole("button", { name: /^DEMO/ }).click();
  await expect(page).toHaveURL(/\/test-cases\/new\?project=/);
  await expect(page.getByLabel("Tiêu đề")).toBeVisible();
});
