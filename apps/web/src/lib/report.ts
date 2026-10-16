/** Tiện ích cho trang Báo cáo. */

export function formatPassRate(rate: number | null | undefined): string {
  return rate == null ? "Chưa có dữ liệu" : `${rate.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}%`;
}

/** Chuỗi query của báo cáo, bỏ các bộ lọc trống. */
export function reportQuery(filters: Record<string, string>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) if (v) p.set(k, v);
  return p.toString();
}
