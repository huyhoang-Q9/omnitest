import type { Priority, TestCaseStatus, TestType } from "./api";

export const TEST_TYPE_LABEL: Record<TestType, string> = {
  api: "API",
  web: "Web",
  desktop_macos: "Desktop macOS",
  desktop_windows: "Desktop Windows",
  mobile_android: "Mobile Android",
  mobile_ios: "Mobile iOS",
};

/** Loại test có adapter ổn định. Desktop/Mobile chạy qua Appium ở mức thử nghiệm (xem APP_TYPES). */
export const RUNNABLE_TYPES: TestType[] = ["api", "web"];

export const PRIORITY_LABEL: Record<Priority, string> = {
  low: "Thấp",
  medium: "Trung bình",
  high: "Cao",
  critical: "Nghiêm trọng",
};

export const CASE_STATUS_LABEL: Record<TestCaseStatus, string> = {
  draft: "Nháp",
  ready: "Sẵn sàng",
  deprecated: "Ngừng dùng",
};

export const WEB_ACTION_LABEL: Record<string, string> = {
  goto: "Mở trang",
  click: "Bấm",
  fill: "Nhập",
  select: "Chọn trong danh sách",
  check: "Đánh dấu",
  uncheck: "Bỏ đánh dấu",
  press: "Nhấn phím",
  wait_for: "Chờ phần tử",
  expect_visible: "Kiểm tra hiển thị",
  expect_hidden: "Kiểm tra bị ẩn",
  expect_text: "Kiểm tra nội dung",
  expect_url: "Kiểm tra URL",
  expect_title: "Kiểm tra tiêu đề trang",
  screenshot: "Chụp màn hình",
};
export const WEB_NEEDS_SELECTOR = new Set([
  "click", "fill", "select", "check", "uncheck", "press", "wait_for", "expect_visible", "expect_hidden", "expect_text",
]);
export const WEB_NEEDS_VALUE = new Set(["goto", "fill", "select", "press", "expect_text", "expect_url", "expect_title"]);

export const ASSERTION_LABEL: Record<string, string> = {
  status: "Mã trạng thái",
  json_path: "Giá trị JSONPath",
  json_schema: "Khớp JSON Schema",
  header: "Header",
  response_time: "Thời gian phản hồi",
};

export const COMPARATOR_LABEL: Record<string, string> = {
  equals: "bằng",
  not_equals: "khác",
  contains: "chứa",
  exists: "tồn tại",
  not_exists: "không tồn tại",
  gt: "lớn hơn",
  lt: "nhỏ hơn",
  matches: "khớp regex",
};

export const ERROR_TYPE_LABEL: Record<string, string> = {
  assertion: "Kiểm tra không đạt",
  timeout: "Quá thời gian",
  connection_error: "Lỗi kết nối",
  blocked_target: "Đích bị chặn bởi chính sách mạng",
  not_supported: "Adapter chưa hỗ trợ",
  missing_variable: "Thiếu biến",
  cancelled: "Đã hủy",
  browser_unavailable: "Không có trình duyệt",
  invalid_definition: "Định nghĩa không hợp lệ",
  adapter_exception: "Lỗi adapter",
};

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "Chưa có";
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} giây`;
  const m = Math.floor(s / 60);
  return `${m} phút ${Math.round(s % 60)} giây`;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/** Desktop/Mobile chạy qua Appium (thử nghiệm). */
export const APP_TYPES: TestType[] = ["desktop_macos", "desktop_windows", "mobile_android", "mobile_ios"];

export const APP_ACTION_LABEL: Record<string, string> = {
  tap: "Chạm / bấm",
  type: "Nhập",
  clear: "Xóa nội dung",
  expect_visible: "Kiểm tra hiển thị",
  expect_hidden: "Kiểm tra bị ẩn",
  expect_text: "Kiểm tra nội dung",
  screenshot: "Chụp màn hình",
  back: "Quay lại",
};
export const APP_NEEDS_LOCATOR = new Set(["tap", "type", "clear", "expect_visible", "expect_hidden", "expect_text"]);
export const APP_NEEDS_VALUE = new Set(["type", "expect_text"]);

export const LOCATOR_STRATEGY_LABEL: Record<string, string> = {
  accessibility_id: "Accessibility ID",
  id: "ID",
  name: "Name",
  xpath: "XPath",
  class_name: "Class name",
  ios_predicate: "iOS predicate",
  ios_class_chain: "iOS class chain",
  android_uiautomator: "Android UiAutomator",
};
