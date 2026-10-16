import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import { STATUS_META } from "@/lib/status";
import { EmptyState, ErrorState } from "./states";
import { StatusBadge } from "./status-badge";

describe("states", () => {
  it("ErrorState có nút thử lại gọi callback", async () => {
    const retry = vi.fn();
    render(<ErrorState message="Hỏng" onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Hỏng");
    await userEvent.click(screen.getByRole("button", { name: /Thử lại/ }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("EmptyState hiển thị tiêu đề", () => {
    render(<EmptyState title="Chưa có dự án nào" />);
    expect(screen.getByText("Chưa có dự án nào")).toBeInTheDocument();
  });

  it("mỗi trạng thái có nhãn tiếng Việt riêng", () => {
    const labels = Object.values(STATUS_META).map((m) => m.label);
    expect(new Set(labels).size).toBe(labels.length);
    render(<StatusBadge status="failed" />);
    expect(screen.getByText("Lỗi")).toBeInTheDocument();
  });
});
