import { describe, expect, it } from "vitest";
import { missingQuickCases, QUICK_CASES, QUICK_TAG, quickCaseBody } from "./quick-check";

describe("bộ kiểm tra nhanh", () => {
  it("chỉ tạo phần còn thiếu, không tạo trùng", () => {
    expect(missingQuickCases([])).toHaveLength(2);
    expect(missingQuickCases([{ title: QUICK_CASES[0].title }]).map((c) => c.title)).toEqual([QUICK_CASES[1].title]);
    expect(missingQuickCases(QUICK_CASES.map((c) => ({ title: c.title })))).toHaveLength(0);
  });

  it("là test case thường: sẵn sàng chạy, gắn tag, định nghĩa khớp loại", () => {
    for (const c of QUICK_CASES) {
      const body = quickCaseBody(c);
      expect(body.status).toBe("ready");
      expect(body.tags).toEqual([QUICK_TAG]);
      expect(body.definition.kind).toBe(body.test_type);
    }
  });
});
