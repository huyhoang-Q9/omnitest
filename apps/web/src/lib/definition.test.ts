import { describe, expect, it } from "vitest";
import { defaultDefinition, formatLoose, hasInvalidJson, INVALID, parseLoose } from "./definition";

describe("định nghĩa test", () => {
  it("giá trị so sánh: số, boolean, null theo JSON, còn lại là chuỗi", () => {
    expect(parseLoose("200")).toBe(200);
    expect(parseLoose("-1.5")).toBe(-1.5);
    expect(parseLoose("true")).toBe(true);
    expect(parseLoose("null")).toBeNull();
    expect(parseLoose("")).toBeNull();
    expect(parseLoose("ok")).toBe("ok");
    expect(parseLoose("0123abc")).toBe("0123abc");
    expect(formatLoose(25)).toBe("25");
    expect(formatLoose("ok")).toBe("ok");
    expect(formatLoose(null)).toBe("");
  });

  it("phát hiện ô JSON đang gõ dở ở mọi độ sâu", () => {
    const def = defaultDefinition("api");
    expect(hasInvalidJson(def)).toBe(false);
    const steps = def.steps as Record<string, unknown>[];
    steps[0].body = { [INVALID]: "{sai" };
    expect(hasInvalidJson(def)).toBe(true);
  });

  it("định nghĩa mặc định khớp loại test", () => {
    expect(defaultDefinition("web").kind).toBe("web");
    expect(defaultDefinition("desktop_macos")).toEqual({ kind: "desktop_macos", notes: "", capabilities: {}, steps: [] });
  });
});
