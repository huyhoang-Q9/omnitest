import { describe, expect, it } from "vitest";
import { formatPassRate, reportQuery } from "./report";

describe("report helpers", () => {
  it("không hiển thị 0% giả khi chưa có dữ liệu", () => {
    expect(formatPassRate(null)).toBe("Chưa có dữ liệu");
    expect(formatPassRate(66.7)).toBe("66,7%");
    expect(formatPassRate(0)).toBe("0%");
  });
  it("bỏ bộ lọc trống", () => {
    expect(reportQuery({ environment_id: "", suite_id: "s1", date_from: "2026-10-01" })).toBe("suite_id=s1&date_from=2026-10-01");
  });
});
