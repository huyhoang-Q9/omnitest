import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, can } from "./api";

afterEach(() => vi.restoreAllMocks());

function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), { status }),
  );
}

describe("api()", () => {
  it("luôn gửi header chống CSRF và JSON body", async () => {
    const f = mockFetch(200, { ok: true });
    await api("/api/x", { method: "POST", json: { a: 1 } });
    const init = f.mock.calls[0][1]!;
    expect((init.headers as Record<string, string>)["X-OmniTest-CSRF"]).toBe("1");
    expect(init.body).toBe('{"a":1}');
  });

  it("trả thông điệp detail của máy chủ", async () => {
    mockFetch(409, { detail: "Mã dự án SHOP đã được dùng" });
    await expect(api("/api/x")).rejects.toMatchObject({ status: 409, message: "Mã dự án SHOP đã được dùng" });
  });

  it("ghép lỗi kiểm tra dữ liệu theo trường", async () => {
    mockFetch(422, { detail: [{ loc: ["body", "key"], msg: "Value error, Mã sai" }] });
    await expect(api("/api/x")).rejects.toThrow("key: Mã sai");
  });

  it("lỗi mạng thành ApiError status 0", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("network"));
    const err = await api("/api/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(0);
  });

  it("204 trả undefined", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));
    await expect(api("/api/x", { method: "DELETE" })).resolves.toBeUndefined();
  });
});

describe("can()", () => {
  it("so sánh thứ bậc vai trò", () => {
    expect(can("admin", "manager")).toBe(true);
    expect(can("tester", "manager")).toBe(false);
    expect(can("viewer", "viewer")).toBe(true);
    expect(can(null, "viewer")).toBe(false);
  });
});
