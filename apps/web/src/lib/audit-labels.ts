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
};

export function auditLabel(action: string): string {
  return LABELS[action] ?? action;
}

export function auditSummary(details: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const k of ["name", "project_key", "email", "variable", "environment", "role", "to"]) {
    const v = details[k];
    if (typeof v === "string" && v) parts.push(v);
  }
  return parts.join(" · ");
}
