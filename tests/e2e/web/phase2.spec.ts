import { expect, test, type Page } from "@playwright/test";

const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "";
const SECRET = "E2E-Secret-Value-123";
const shots = "../../artifacts/e2e/screenshots";

test.skip(!EMAIL || !PASSWORD, "Cần E2E_ADMIN_EMAIL và E2E_ADMIN_PASSWORD");

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Mật khẩu").fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByRole("heading", { name: "Cổng kiểm thử tự động OmniTest" })).toBeVisible();
}

test("chưa đăng nhập bị chuyển về trang login, sai mật khẩu báo lỗi", async ({ page }, info) => {
  await page.goto("/projects");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByText("Vui lòng nhập email")).toBeVisible();
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Mật khẩu").fill("Sai-mat-khau-1");
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Email hoặc mật khẩu không đúng" })).toBeVisible();
  await page.screenshot({ path: `${shots}/${info.project.name}-login-error.png`, fullPage: true });
});

test("luồng chính: dự án, môi trường, biến secret, lưu trữ", async ({ page }, info) => {
  const key = `E${info.project.name === "mobile" ? "M" : "D"}${Date.now().toString(36).toUpperCase().slice(-6)}`;
  await login(page);
  await page.screenshot({ path: `${shots}/${info.project.name}-dashboard.png`, fullPage: true });

  // Tạo dự án
  await page.goto("/projects?new=1");
  await page.getByLabel("Mã dự án").fill(key.toLowerCase());
  await page.getByLabel("Tên dự án").fill(`Dự án E2E ${key}`);
  await page.getByRole("button", { name: "Tạo dự án" }).last().click();
  await expect(page.getByRole("heading", { name: new RegExp(`Dự án E2E ${key}`) })).toBeVisible();
  await expect(page.getByText("Chưa có môi trường")).toBeVisible();

  // Thêm môi trường UAT: mặc định cần xác nhận trước khi chạy
  await page.getByRole("button", { name: "Thêm môi trường" }).first().click();
  const dlg = page.getByRole("dialog");
  await dlg.getByLabel("Tên").fill("UAT");
  await dlg.getByLabel("Loại").selectOption("uat");
  await dlg.getByLabel("Base URL").fill("ftp://sai");
  await dlg.getByRole("button", { name: "Thêm môi trường" }).click();
  await expect(dlg.getByText("URL phải bắt đầu bằng http:// hoặc https://")).toBeVisible();
  await dlg.getByLabel("Base URL").fill("https://uat.example.vn");
  await dlg.getByRole("button", { name: "Thêm môi trường" }).click();
  await expect(page.getByText("Đã tạo môi trường UAT")).toBeVisible();
  await page.getByRole("link", { name: /UAT/ }).click();
  await expect(page.getByText("Cần xác nhận trước khi chạy")).toBeVisible();

  // Biến secret: lưu xong không hiển thị lại giá trị
  await page.getByRole("button", { name: "Thêm biến" }).first().click();
  const vd = page.getByRole("dialog");
  await vd.getByLabel("Tên biến").fill("API_TOKEN");
  await vd.getByRole("switch").click();
  await vd.getByLabel("Giá trị").fill(SECRET);
  await vd.getByRole("button", { name: "Thêm biến" }).click();
  await expect(page.getByText("Đã đặt (ẩn)")).toBeVisible();
  await expect(page.locator("body")).not.toContainText(SECRET);
  await page.screenshot({ path: `${shots}/${info.project.name}-environment.png`, fullPage: true });

  // Xóa biến cần xác nhận
  await page.getByRole("button", { name: "Xóa API_TOKEN" }).click();
  await expect(page.getByRole("alertdialog")).toContainText("Xóa biến API_TOKEN?");
  await page.getByRole("button", { name: "Hủy" }).click();
  await expect(page.getByText("API_TOKEN")).toBeVisible();

  // Lưu trữ dự án có xác nhận, sau đó chỉ xem
  await page.getByRole("link", { name: `Dự án E2E ${key}` }).click();
  await page.getByRole("button", { name: "Lưu trữ" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Lưu trữ" }).click();
  await expect(page.getByText("Dự án đang lưu trữ nên chỉ xem được")).toBeVisible();
  await page.getByRole("button", { name: "Khôi phục" }).click();
  await expect(page.getByText("Đã khôi phục dự án")).toBeVisible();
  await page.screenshot({ path: `${shots}/${info.project.name}-project.png`, fullPage: true });
});

test("AI chưa cấu hình hiển thị rõ, không giả lập kết quả", async ({ page }) => {
  await login(page);
  const status = await (await page.request.get("/api/ai/status")).json();
  test.skip(status.configured, "API đang chạy với AI được cấu hình");
  await page.goto("/ai");
  await expect(page.getByText("AI chưa được cấu hình")).toBeVisible();
});
