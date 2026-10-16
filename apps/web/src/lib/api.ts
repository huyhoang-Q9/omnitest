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
export type TestCase = Schemas["TestCaseOut"];
export type TestCaseVersion = Schemas["TestCaseVersionOut"];
export type TestType = Schemas["TestType"];
export type Priority = Schemas["Priority"];
export type TestCaseStatus = Schemas["TestCaseStatus"];
export type ImportResult = Schemas["ImportResult"];
export type OpenApiImportResult = Schemas["OpenApiImportResult"];
export type ProjectReport = Schemas["ProjectReportOut"];
export type ReportGroup = Schemas["GroupStat"];
export type AIStatus = Schemas["AIStatusOut"];
export type AISuggestion = Schemas["SuggestionResult"];
export type AIDraft = Schemas["Draft"];
export type FailureAnalysis = Schemas["FailureAnalysisResult"];
export type Suite = Schemas["SuiteOut"];
export type SuiteDetail = Schemas["SuiteDetailOut"];
export type Run = Schemas["RunOut"];
export type RunDetail = Schemas["RunDetailOut"];
export type RunItem = Schemas["RunItemOut"];
export type RunItemDetail = Schemas["RunItemDetailOut"];
export type StepResult = Schemas["StepResultOut"];
export type Artifact = Schemas["ArtifactOut"];
export type Adapter = Schemas["AdapterOut"];
export type ApiStep = Schemas["ApiStep"];
export type WebStep = Schemas["WebStep"];
export type ApiDefinition = Schemas["ApiTestDefinition"];
export type WebDefinition = Schemas["WebTestDefinition"];
export type Page<T> = { items: T[]; total: number; page: number; page_size: number };

/** Chi tiết lỗi có cấu trúc, VD 409 cần xác nhận trước khi chạy: {code, message, reasons}. */
export type ErrorDetail = { code?: string; message?: string; reasons?: string[] };

export class ApiError extends Error {
  readonly status: number;
  readonly detail: ErrorDetail | null;
  constructor(status: number, message: string, detail: ErrorDetail | null = null) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail) && typeof (detail as ErrorDetail).message === "string")
    return (detail as ErrorDetail).message as string;
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
  if (!res.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    const structured = detail && typeof detail === "object" && !Array.isArray(detail) ? (detail as ErrorDetail) : null;
    throw new ApiError(res.status, errorMessage(res.status, body), structured);
  }
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
