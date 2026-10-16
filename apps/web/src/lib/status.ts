/** Màu trạng thái thống nhất toàn hệ thống (dùng cho test run, test case, bước). */
export type RunStatus = "queued" | "running" | "passed" | "failed" | "skipped" | "blocked" | "cancelled" | "error";

export const STATUS_META: Record<RunStatus, { label: string; className: string }> = {
  queued: { label: "Đang chờ", className: "bg-status-queued/12 text-status-queued" },
  running: { label: "Đang chạy", className: "bg-status-running/12 text-status-running" },
  passed: { label: "Đạt", className: "bg-status-passed/12 text-status-passed" },
  failed: { label: "Lỗi", className: "bg-status-failed/12 text-status-failed" },
  skipped: { label: "Bỏ qua", className: "bg-status-skipped/15 text-status-skipped" },
  blocked: { label: "Bị chặn", className: "bg-status-blocked/15 text-status-blocked" },
  cancelled: { label: "Đã hủy", className: "bg-status-cancelled/12 text-status-cancelled" },
  error: { label: "Lỗi hệ thống", className: "bg-status-failed/12 text-status-failed" },
};

export const isActive = (s: RunStatus) => s === "queued" || s === "running";
