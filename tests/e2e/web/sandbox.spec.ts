import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Cần stack thật với sandbox bật: API và worker chạy với OMNITEST_SANDBOX_ENABLED=true, máy worker có Docker và
// image omnitest-sandbox (docker build -f infra/docker/sandbox.Dockerfile -t omnitest-sandbox:latest .).
// Sandbox chưa bật thì test tự bỏ qua.
const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "";
const shots = "../../artifacts/e2e/screenshots";
const CSRF = { "X-OmniTest-CSRF": "1" };
const TITLE = "[E2E sandbox] Script pytest";

test.skip(!EMAIL || !PASSWORD, "Cần E2E_ADMIN_EMAIL và E2E_ADMIN_PASSWORD");

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Mật khẩu").fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByRole("heading", { name: "Cổng kiểm thử tự động OmniTest" })).toBeVisible();
  const adapters = await (await page.request.get("/api/adapters")).json();
  const sandbox = adapters.find((a: { test_kinds: string[] }) => a.test_kinds.includes("script"));
  test.skip(!sandbox?.environment_ok, "Máy chủ chưa bật sandbox script code");
}

async function demoProject(request: APIRequestContext) {
  const projects = await (await request.get("/api/projects?page_size=100")).json();
  const demo = projects.items.find((p: { key: string }) => p.key === "DEMO");
  expect(demo, "Chưa có dự án DEMO").toBeTruthy();
  return demo as { id: string };
}

async function cleanup(request: APIRequestContext, projectId: string) {
  const list = await (await request.get(`/api/projects/${projectId}/test-cases?page_size=100&q=${encodeURIComponent(TITLE)}`)).json();
  for (const c of list.items) await request.delete(`/api/test-cases/${c.id}`, { headers: CSRF });
}

test("Admin bật script code, viết test pytest và chạy trong sandbox Docker", async ({ page }, info) => {
  test.setTimeout(150_000);
  await login(page);
  const demo = await demoProject(page.request);
  await cleanup(page.request, demo.id);

  await page.goto(`/projects/${demo.id}`);
  const toggle = page.getByRole("switch", { name: "Cho phép test script code (pytest/Playwright)" });
  if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "true");

  await page.goto(`/test-cases/new?project=${demo.id}`);
  await page.getByLabel("Tiêu đề").fill(TITLE);
  await page.getByLabel("Loại test").selectOption("script");
  await expect(page.getByRole("note")).toContainText("container Docker cô lập");
  await page.getByLabel("Nội dung test_main.py").fill(
    [
      "import os",
      "",
      "def test_co_bien_moi_truong():",
      "    assert os.environ['OMNITEST_BASE_URL'].startswith('http')",
      "",
      "def test_trinh_duyet(page):",
      "    page.set_content('<h1>OmniTest</h1>')",
      "    page.screenshot(path=os.environ['OMNITEST_ARTIFACTS_DIR'] + '/man-hinh.png')",
      "    assert page.inner_text('h1') == 'OmniTest'",
      "",
    ].join("\n"),
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.visualViewport!.width + 1)).toBe(true);
  await page.screenshot({ path: `${shots}/${info.project.name}-script-editor.png`, fullPage: true });
  await page.getByRole("button", { name: "Tạo test case" }).click();
  await expect(page.getByText(/Đã tạo DEMO-TC-/)).toBeVisible();

  await page.getByRole("button", { name: "Chạy", exact: true }).click();
  const dlg = page.getByRole("dialog");
  await dlg.getByRole("button", { name: "Chạy", exact: true }).click();
  await expect(dlg.getByText(/sẽ chạy trong sandbox Docker/)).toBeVisible();
  await dlg.getByRole("button", { name: "Tôi xác nhận, chạy" }).click();

  await expect(page).toHaveURL(/\/test-runs\/[0-9a-f-]+$/);
  await expect(page.getByText("1/1 xong")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("1 đạt")).toBeVisible();
  await page.getByRole("button", { name: new RegExp(TITLE.replace(/[[\]]/g, "\\$&")) }).click();
  await expect(page.getByText("test_main::test_trinh_duyet[chromium]")).toBeVisible();
  await expect(page.getByRole("link", { name: /pytest-output\.txt/ })).toBeVisible();
  await page.screenshot({ path: `${shots}/${info.project.name}-script-run.png`, fullPage: true });

  await cleanup(page.request, demo.id);
});
