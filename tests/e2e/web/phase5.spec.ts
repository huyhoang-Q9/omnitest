import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Cần API chạy với nhà cung cấp AI là test double (tests/e2e/fake_llm.py), KHÔNG phải AI thật:
//   OMNITEST_AI_PROVIDER=openai_compatible OMNITEST_AI_BASE_URL=http://127.0.0.1:8199/v1 OMNITEST_AI_MODEL=fake
// Không có AI thì các test này tự bỏ qua.
const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "";
const shots = "../../artifacts/e2e/screenshots";
const CSRF = { "X-OmniTest-CSRF": "1" };

test.skip(!EMAIL || !PASSWORD, "Cần E2E_ADMIN_EMAIL và E2E_ADMIN_PASSWORD");

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Mật khẩu").fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  const status = await (await page.request.get("/api/ai/status")).json();
  test.skip(!status.configured, "API chưa chạy với nhà cung cấp AI (test double)");
}

async function demoProject(request: APIRequestContext) {
  const projects = await (await request.get("/api/projects?page_size=100")).json();
  const demo = projects.items.find((p: { key: string }) => p.key === "DEMO");
  expect(demo, "Chưa có dự án DEMO").toBeTruthy();
  return demo as { id: string; ai_enabled: boolean };
}

async function deleteCasesByTitle(request: APIRequestContext, projectId: string, prefix: string) {
  const list = await (await request.get(`/api/projects/${projectId}/test-cases?page_size=100&q=${encodeURIComponent(prefix)}`)).json();
  for (const c of list.items) await request.delete(`/api/test-cases/${c.id}`, { headers: CSRF });
}

test("bật AI cho dự án, đề xuất test case, duyệt rồi lưu ở trạng thái Nháp", async ({ page }, info) => {
  await login(page);
  const demo = await demoProject(page.request);
  await page.goto(`/projects/${demo.id}`);
  const toggle = page.getByRole("switch", { name: "Cho phép dùng Trợ lý AI trong dự án" });
  if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "true");

  await page.goto(`/ai?project=${demo.id}`);
  await page.getByLabel("Mô tả yêu cầu hoặc chức năng cần test").fill("Kiểm tra API health của ứng dụng kho hàng mini");
  await page.getByRole("button", { name: "Đề xuất test case" }).click();
  const region = page.getByRole("region", { name: "Đề xuất của AI" });
  await expect(region.getByText("chưa được lưu")).toBeVisible();
  await expect(region.getByText("[AI giả lập] Health trả 200")).toBeVisible();
  await expect(region.getByText("Không hợp lệ, không lưu được")).toBeVisible();
  await expect(region.getByLabel("[AI giả lập] Định nghĩa sai")).toBeDisabled();
  await expect(region.getByLabel("[AI giả lập] Health trả 200")).toBeChecked();
  await page.screenshot({ path: `${shots}/${info.project.name}-ai-suggest.png`, fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.visualViewport!.width + 1)).toBe(true);

  await region.getByRole("button", { name: "Lưu 1 test case đã chọn" }).click();
  await expect(page.getByText("Đã lưu 1 test case ở trạng thái Nháp")).toBeVisible();
  const list = await (await page.request.get(`/api/projects/${demo.id}/test-cases?q=${encodeURIComponent("[AI giả lập]")}`)).json();
  expect(list.items).toHaveLength(1);
  expect(list.items[0].status).toBe("draft");
  expect(list.items[0].tags).toContain("ai");
  await deleteCasesByTitle(page.request, demo.id, "[AI giả lập]");
});

test("phân tích lỗi bằng AI ở chi tiết lần chạy", async ({ page }, info) => {
  test.setTimeout(90_000);
  await login(page);
  const demo = await demoProject(page.request);
  await page.request.patch(`/api/projects/${demo.id}`, { headers: CSRF, data: { ai_enabled: true } });
  const envs = await (await page.request.get(`/api/projects/${demo.id}/environments`)).json();
  const tc = await (
    await page.request.post(`/api/projects/${demo.id}/test-cases`, {
      headers: CSRF,
      data: {
        title: "[E2E AI] Mong đợi sai mã",
        test_type: "api",
        definition: { kind: "api", steps: [{ name: "Health", url: "/api/health", assertions: [{ type: "status", equals: 418 }] }] },
      },
    })
  ).json();
  const run = await (
    await page.request.post(`/api/projects/${demo.id}/runs`, {
      headers: CSRF,
      data: { environment_id: envs[0].id, test_case_ids: [tc.id], confirm: true },
    })
  ).json();
  await page.goto(`/test-runs/${run.id}`);
  await expect(page.getByText("1/1 xong")).toBeVisible({ timeout: 60_000 });
  // Test không đạt đầu tiên được mở sẵn.
  await page.getByRole("button", { name: "Phân tích lỗi bằng AI" }).click();
  const box = page.getByRole("region", { name: "Phân tích của AI" });
  await expect(box.getByText("tham khảo, cần người kiểm tra lại")).toBeVisible();
  await expect(box.getByText("Lỗi ở test")).toBeVisible();
  await expect(box.getByText("Sửa assertion về 200")).toBeVisible();
  await page.screenshot({ path: `${shots}/${info.project.name}-ai-analyze.png`, fullPage: true });
  await page.request.delete(`/api/test-cases/${tc.id}`, { headers: CSRF });
});
