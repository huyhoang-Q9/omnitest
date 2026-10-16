import type { TestCase, TestType } from "./api";
import type { Definition } from "./definition";

/** Tag đánh dấu bộ "Kiểm tra nhanh" do portal tạo; dùng lại nếu dự án đã có, không tạo trùng. */
export const QUICK_TAG = "kiem-tra-nhanh";

type QuickCase = {
  title: string;
  description: string;
  test_type: TestType;
  expected_result: string;
  definition: Definition;
};

/** Hai kiểm tra cơ bản cho mọi hệ thống web: trang gốc trả lời hợp lệ, trang mở được trong trình duyệt. */
export const QUICK_CASES: QuickCase[] = [
  {
    title: "Kiểm tra nhanh: hệ thống phản hồi",
    description: "Gọi trang gốc của môi trường, kiểm tra mã phản hồi thành công và thời gian phản hồi.",
    test_type: "api",
    expected_result: "Mã 2xx (sau khi theo chuyển hướng), phản hồi dưới 5 giây.",
    definition: {
      kind: "api",
      steps: [
        {
          name: "Trang gốc phản hồi",
          method: "GET",
          url: "/",
          assertions: [
            { type: "status", one_of: [200, 201, 202, 203, 204] },
            { type: "response_time", max_ms: 5000 },
          ],
        },
      ],
    },
  },
  {
    title: "Kiểm tra nhanh: trang web mở được",
    description: "Mở trang gốc bằng Chromium, chờ nội dung hiển thị và chụp ảnh màn hình làm bằng chứng.",
    test_type: "web",
    expected_result: "Trang tải xong, có nội dung hiển thị, có ảnh chụp màn hình.",
    definition: {
      kind: "web",
      browser: "chromium",
      viewport: { width: 1280, height: 800 },
      trace: "on_failure",
      steps: [
        { name: "Mở trang gốc", action: "goto", value: "/" },
        { name: "Nội dung hiển thị", action: "expect_visible", selector: "body" },
        { name: "Chụp màn hình", action: "screenshot" },
      ],
    },
  },
];

export function quickCaseBody(c: QuickCase) {
  return { ...c, status: "ready" as const, priority: "high" as const, tags: [QUICK_TAG] };
}

/** Bộ kiểm tra nhanh đã đủ khi dự án có đúng các tiêu đề trên (tìm theo tag, bỏ test đã xóa). */
export function missingQuickCases(existing: Pick<TestCase, "title">[]): QuickCase[] {
  const titles = new Set(existing.map((t) => t.title));
  return QUICK_CASES.filter((c) => !titles.has(c.title));
}
