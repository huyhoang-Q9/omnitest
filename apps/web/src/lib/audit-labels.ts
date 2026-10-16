const LABELS: Record<string, string> = {
  "auth.login": "Đăng nhập",
  "auth.login_failed": "Đăng nhập thất bại",
  "auth.login_locked": "Đăng nhập khi tài khoản đang khóa",
  "user.create": "Tạo người dùng",
  "project.create": "Tạo dự án",
  "project.update": "Cập nhật dự án",
  "project.archive": "Lưu trữ dự án",
  "project.restore": "Khôi phục dự án",
  "member.add": "Thêm thành viên",
  "member.update_role": "Đổi vai trò thành viên",
  "member.remove": "Gỡ thành viên",
  "environment.create": "Tạo môi trường",
  "environment.update": "Cập nhật môi trường",
  "environment.delete": "Xóa môi trường",
  "variable.create": "Thêm biến",
  "variable.update": "Cập nhật biến",
  "variable.delete": "Xóa biến",
  "test_case.create": "Tạo test case",
  "test_case.update": "Sửa test case",
  "test_case.duplicate": "Nhân bản test case",
  "test_case.delete": "Xóa test case",
  "test_case.restore": "Khôi phục test case",
  "test_case.import": "Nhập test case từ file",
  "test_case.export": "Xuất test case",
  "suite.create": "Tạo suite",
  "suite.update": "Sửa suite",
  "suite.set_items": "Cập nhật test case của suite",
  "suite.delete": "Xóa suite",
  "run.create": "Chạy test",
  "run.cancel": "Hủy lần chạy",
};

export function auditLabel(action: string): string {
  return LABELS[action] ?? action;
}

export function auditSummary(details: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const k of ["code", "name", "project_key", "email", "variable", "environment", "role", "to"]) {
    const v = details[k];
    if (typeof v === "string" && v) parts.push(v);
  }
  return parts.join(" · ");
}
