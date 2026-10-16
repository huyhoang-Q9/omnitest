import { expect, test, type Page } from "@playwright/test";

// Chạy trên stack thật: API + worker Dramatiq + Redis + demo-target, sau khi đã chạy
//   uv run omnitest-api seed-demo --owner-email <E2E_ADMIN_EMAIL>
const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "";
const shots = "../../artifacts/e2e/screenshots";

test.skip(!EMAIL || !PASSWORD, "Cần E2E_ADMIN_EMAIL và E2E_ADMIN_PASSWORD");

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Mật khẩu").fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
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

test("chạy suite Smoke qua worker thật, xem kết quả từng bước", async ({ page }, info) => {
  test.setTimeout(120_000);
  await login(page);
  await openDemoProject(page, "/test-suites");
  await page.getByRole("link", { name: "Smoke" }).click();
  await expect(page.getByRole("heading", { name: "Smoke" })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.getByRole("button", { name: "Chạy suite" }).click();

  const dlg = page.getByRole("dialog");
  await expect(dlg.getByLabel("Môi trường")).toBeVisible();
  await dlg.getByRole("button", { name: "Chạy", exact: true }).click();
  // Suite có test POST nên máy chủ yêu cầu xác nhận, hiển thị lý do.
  await expect(dlg.getByText("Cần xác nhận trước khi chạy")).toBeVisible();
  await expect(dlg.getByText(/có thể thay đổi dữ liệu/)).toBeVisible();
  await page.screenshot({ path: `${shots}/${info.project.name}-run-confirm.png` });
  await dlg.getByRole("button", { name: "Tôi xác nhận, chạy" }).click();

  await expect(page).toHaveURL(/\/test-runs\/[0-9a-f-]+$/);
  await expect(page.getByRole("heading", { name: "Suite Smoke" })).toBeVisible();
  // Chờ worker chạy xong (trang tự cập nhật).
  await expect(page.getByText("4/4 xong")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText("4 đạt")).toBeVisible();

  // Mở test web: có các bước và ảnh chụp màn hình thật.
  await page.getByRole("button", { name: /Web đăng nhập thành công/ }).click();
  await expect(page.getByRole("button", { name: /Chụp màn hình/ })).toBeVisible();
  await page.getByRole("button", { name: /Chụp màn hình/ }).click();
  const img = page.getByRole("img", { name: /Ảnh chụp/ });
  await expect(img).toBeVisible();
  expect(await img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(100);
  // Secret không lộ ra giao diện.
  await expect(page.getByText("Demo@123")).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: `${shots}/${info.project.name}-run-detail.png`, fullPage: true });

  for (const [path, heading] of [["/test-cases", "Test case"], ["/test-suites", "Test suite"], ["/test-runs", "Lần chạy"]]) {
    await openDemoProject(page, path);
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: `${shots}/${info.project.name}-${path.slice(1)}.png`, fullPage: true });
  }

  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Kết quả 14 ngày/ })).toBeVisible();
  await expect(page.getByText(/Tỷ lệ đạt/)).toBeVisible();
  await page.screenshot({ path: `${shots}/${info.project.name}-dashboard-phase3.png`, fullPage: true });
});

test("tạo test case API bằng trình soạn bước, sửa tạo phiên bản mới, xóa và khôi phục", async ({ page }, info) => {
  const title = `API health E2E ${info.project.name} ${Date.now().toString(36)}`;
  await login(page);
  await openDemoProject(page, "/test-cases");
  await page.getByRole("link", { name: "Tạo test case" }).click();
  await expect(page.getByRole("heading", { name: "Tạo test case" })).toBeVisible();

  await page.getByLabel("Tiêu đề").fill(title);
  await page.getByLabel("Nhãn").fill("e2e, smoke");
  await page.getByLabel("Tên bước").fill("Gọi health");
  await page.getByLabel("URL").fill("/api/health");
  // JSON body sai bị chặn trước khi gửi.
  await page.getByLabel("Body").selectOption("json");
  await page.getByLabel("Nội dung JSON").fill("{sai");
  await expect(page.getByText("JSON không hợp lệ")).toBeVisible();
  await page.getByRole("button", { name: "Tạo test case" }).click();
  await expect(page.getByText("Còn ô JSON không hợp lệ")).toBeVisible();
  await page.getByLabel("Body").selectOption("none");

  await page.getByRole("button", { name: "Tạo test case" }).click();
  await expect(page.getByText(/Đã tạo DEMO-TC-\d+/)).toBeVisible();
  // Không bị tràn ngang trên màn hình nhỏ.
  await expectNoHorizontalOverflow(page);
  await expect(page).toHaveURL(/\/test-cases\/[0-9a-f-]+$/);
  await expect(page.getByText("Phiên bản 1 ·").first()).toBeVisible();

  await page.getByLabel("Mức ưu tiên").selectOption("high");
  await page.getByLabel("Ghi chú thay đổi").fill("tăng ưu tiên");
  await page.getByRole("button", { name: "Lưu thay đổi" }).click();
  await expect(page.getByText(/phiên bản 2/)).toBeVisible();
  await expect(page.getByText("“tăng ưu tiên”")).toBeVisible();
  await page.screenshot({ path: `${shots}/${info.project.name}-test-case-editor.png`, fullPage: true });

  await page.getByRole("button", { name: "Xóa", exact: true }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Xóa", exact: true }).click();
  await expect(page.getByText("Đã xóa", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Khôi phục" }).click();
  await expect(page.getByText("Đã khôi phục test case")).toBeVisible();
});

test("test desktop lưu được nhưng hiển thị rõ là chưa chạy được", async ({ page }) => {
  await login(page);
  await openDemoProject(page, "/test-cases");
  await page.getByRole("link", { name: "Tạo test case" }).click();
  await page.getByLabel("Loại test").selectOption("desktop_macos");
  await expect(page.getByRole("note")).toContainText("chưa có adapter chạy thật");
  await expect(page.getByRole("note")).toContainText("Bị chặn");
});
