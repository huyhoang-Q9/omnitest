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

export const SCRIPT_TEMPLATE = `import os

import httpx

BASE_URL = os.environ["OMNITEST_BASE_URL"]


def test_trang_chu_tra_200():
    # Cần chọn "Mạng: qua proxy của môi trường" để gọi được hệ thống đích.
    r = httpx.get(BASE_URL, timeout=10)
    assert r.status_code == 200


# Playwright: dùng fixture page; base_url lấy từ Base URL của môi trường.
# def test_tieu_de(page):
#     page.goto("/")
#     assert "Kho hàng" in page.title()
`;

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
  if (type === "script") return { kind: "script", runner: "pytest", network: "none", files: { "test_main.py": SCRIPT_TEMPLATE } };
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

