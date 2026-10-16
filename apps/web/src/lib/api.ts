import type { components } from "./api-types";

export type Schemas = components["schemas"];
export type User = Schemas["UserOut"];
export type Project = Schemas["ProjectOut"];
export type ProjectRole = Schemas["ProjectRole"];
export type Member = Schemas["MemberOut"];
export type Environment = Schemas["EnvironmentOut"];
export type EnvironmentKind = Schemas["EnvironmentKind"];
export type Variable = Schemas["VariableOut"];
export type Dashboard = Schemas["DashboardOut"];
export type AuditEntry = Schemas["AuditOut"];
export type Page<T> = { items: T[]; total: number; page: number; page_size: number };

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // Lỗi kiểm tra dữ liệu của FastAPI: ghép thông điệp từng trường.
    return detail
      .map((d: { msg?: string; loc?: unknown[] }) => {
        const field = Array.isArray(d.loc) ? d.loc.filter((x) => x !== "body").join(".") : "";
        const msg = (d.msg ?? "").replace(/^Value error, /, "");
        return field ? `${field}: ${msg}` : msg;
      })
      .join("; ");
  }
  if (status === 0) return "Không kết nối được máy chủ";
  if (status >= 500) return "Máy chủ gặp lỗi, vui lòng thử lại";
  return `Yêu cầu thất bại (${status})`;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(path, {
      credentials: "same-origin",
      ...rest,
      headers: {
        Accept: "application/json",
        "X-OmniTest-CSRF": "1",
        ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
        ...headers,
      },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch {
    throw new ApiError(0, errorMessage(0, null));
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, errorMessage(res.status, body));
  return body as T;
}

export const ROLE_LABEL: Record<ProjectRole, string> = {
  admin: "Admin",
  manager: "Manager",
  tester: "Tester",
  viewer: "Viewer",
};

export const ROLE_RANK: Record<ProjectRole, number> = { viewer: 1, tester: 2, manager: 3, admin: 4 };

export function can(role: ProjectRole | null | undefined, minimum: ProjectRole): boolean {
  return !!role && ROLE_RANK[role] >= ROLE_RANK[minimum];
}

export const ENV_KIND_LABEL: Record<EnvironmentKind, string> = {
  dev: "Dev",
  test: "Test",
  uat: "UAT",
  staging: "Staging",
};
