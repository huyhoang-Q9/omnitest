import type { TestType } from "./api";

export type Obj = Record<string, unknown>;
export type Definition = Obj & { kind: string };

/** Ô JSON đang gõ dở được lưu dưới dạng này để không mất nội dung; chặn lưu khi còn tồn tại. */
export const INVALID = "__invalid_json__";

export function hasInvalidJson(v: unknown): boolean {
  if (Array.isArray(v)) return v.some(hasInvalidJson);
  if (v && typeof v === "object") {
    if (INVALID in v) return true;
    return Object.values(v).some(hasInvalidJson);
  }
  return false;
}

export function defaultDefinition(type: TestType): Definition {
  if (type === "api")
    return { kind: "api", steps: [{ name: "Bước 1", method: "GET", url: "/", assertions: [{ type: "status", equals: 200 }] }] };
  if (type === "web")
    return {
      kind: "web",
      browser: "chromium",
      viewport: { width: 1280, height: 800 },
      trace: "on_failure",
      steps: [{ name: "Mở trang", action: "goto", value: "/" }],
    };
  return { kind: type, notes: "", capabilities: {}, steps: [] };
}

/** Giá trị so sánh: số, true/false, null được hiểu theo JSON, còn lại là chuỗi. */
export function parseLoose(text: string): unknown {
  const t = text.trim();
  if (t === "") return null;
  if (/^-?\d+(\.\d+)?$/.test(t) || t === "true" || t === "false" || t === "null") return JSON.parse(t);
  return text;
}

export function formatLoose(v: unknown): string {
  if (v === null || v === undefined) return "";
  return typeof v === "string" ? v : JSON.stringify(v);
}

