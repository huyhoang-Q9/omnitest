import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, Copy, History, Play, Save, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { FormField } from "@/components/form-field";
import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingState } from "@/components/states";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { RunDialog } from "@/features/run-dialog";
import { DefinitionEditor } from "@/features/steps-editor";
import { defaultDefinition, hasInvalidJson, type Definition } from "@/lib/definition";
import {
  api,
  ApiError,
  can,
  type Priority,
  type Project,
  type TestCase,
  type TestCaseStatus,
  type TestCaseVersion,
  type TestType,
} from "@/lib/api";
import { CASE_STATUS_LABEL, PRIORITY_LABEL, TEST_TYPE_LABEL } from "@/lib/test-labels";
import { formatDateTime } from "@/lib/utils";

type FormState = {
  title: string;
  description: string;
  test_type: TestType;
  priority: Priority;
  status: TestCaseStatus;
  tags: string;
  preconditions: string;
  expected_result: string;
  side_effect: boolean;
  retry_count: number;
  timeout_seconds: number;
  definition: Definition;
  change_note: string;
};

const FIELD_LABEL: Record<string, string> = {
  title: "tiêu đề",
  description: "mô tả",
  test_type: "loại",
  priority: "ưu tiên",
  status: "trạng thái",
  tags: "nhãn",
  preconditions: "điều kiện",
  expected_result: "kết quả mong đợi",
  test_data: "dữ liệu test",
  definition: "các bước",
  side_effect: "thay đổi dữ liệu",
  retry_count: "số lần thử lại",
  timeout_seconds: "thời gian tối đa",
};

function fromCase(tc: TestCase | undefined): FormState {
  const type = tc?.test_type ?? "api";
  return {
    title: tc?.title ?? "",
    description: tc?.description ?? "",
    test_type: type,
    priority: tc?.priority ?? "medium",
    status: tc?.status ?? "draft",
    tags: (tc?.tags ?? []).join(", "),
    preconditions: tc?.preconditions ?? "",
    expected_result: tc?.expected_result ?? "",
    side_effect: tc?.side_effect ?? false,
    retry_count: tc?.retry_count ?? 0,
    timeout_seconds: tc?.timeout_seconds ?? 300,
    definition: (tc?.definition as Definition | undefined) ?? defaultDefinition(type),
    change_note: "",
  };
}

function VersionsPanel({ caseId }: { caseId: string }) {
  const q = useQuery({ queryKey: ["test-case-versions", caseId], queryFn: () => api<TestCaseVersion[]>(`/api/test-cases/${caseId}/versions`) });
  if (q.isPending) return <LoadingState rows={2} />;
  if (q.isError) return <ErrorState message={q.error.message} onRetry={() => q.refetch()} />;
  return (
    <ol className="space-y-3 text-sm">
      {q.data.map((v) => (
        <li key={v.id} className="rounded-md border p-3">
          <p className="font-medium">
            Phiên bản {v.version}
            <span className="font-normal text-muted-foreground"> · {formatDateTime(v.created_at)}</span>
          </p>
          <p className="text-xs text-muted-foreground">{v.changed_by_email ?? "Hệ thống"}</p>
          <p className="mt-1">
            {v.version === 1 && v.changed_fields.length === 0
              ? "Tạo mới"
              : `Đổi: ${v.changed_fields.map((f) => FIELD_LABEL[f] ?? f).join(", ") || "tạo mới"}`}
          </p>
          {v.change_note && <p className="mt-1 italic text-muted-foreground">“{v.change_note}”</p>}
        </li>
      ))}
    </ol>
  );
}

export function TestCaseEditorPage() {
  const { caseId } = useParams();
  const [params] = useSearchParams();
  const tcq = useQuery({ queryKey: ["test-case", caseId], queryFn: () => api<TestCase>(`/api/test-cases/${caseId}`), enabled: !!caseId });
  const projectId = caseId ? tcq.data?.project_id : params.get("project");
  const pq = useQuery({ queryKey: ["project", projectId], queryFn: () => api<Project>(`/api/projects/${projectId}`), enabled: !!projectId });
  if (caseId && tcq.isPending) return <LoadingState rows={6} />;
  if (caseId && tcq.isError) return <ErrorState message={tcq.error.message} onRetry={() => tcq.refetch()} />;
  if (!projectId) return <ErrorState message="Chưa chọn dự án. Hãy tạo test case từ trang danh sách." />;
  const tc = tcq.data;
  // Dựng lại form theo phiên bản máy chủ (sau khi lưu, khôi phục...) thay vì đồng bộ state bằng effect.
  return <TestCaseEditor key={tc ? `${tc.id}-${tc.version}-${tc.is_deleted}` : "new"} tc={tc} projectId={projectId} project={pq.data} />;
}

function TestCaseEditor({ tc, projectId, project }: { tc: TestCase | undefined; projectId: string; project: Project | undefined }) {
  const caseId = tc?.id;
  const isNew = !tc;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [form, setForm] = useState<FormState>(() => fromCase(tc));
  const [formKey, setFormKey] = useState(0);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [runOpen, setRunOpen] = useState(false);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setForm((f) => ({ ...f, [k]: v }));
  const role = project?.my_role;
  const canEdit = can(role, "manager") && !project?.is_archived && !tc?.is_deleted;

  const save = useMutation({
    mutationFn: () => {
      const body = {
        title: form.title,
        description: form.description,
        test_type: form.test_type,
        priority: form.priority,
        status: form.status,
        tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
        preconditions: form.preconditions,
        expected_result: form.expected_result,
        side_effect: form.side_effect,
        retry_count: form.retry_count,
        timeout_seconds: form.timeout_seconds,
        definition: form.definition,
      };
      return isNew
        ? api<TestCase>(`/api/projects/${projectId}/test-cases`, { method: "POST", json: body })
        : api<TestCase>(`/api/test-cases/${caseId}`, {
            method: "PATCH",
            json: { ...body, version: tc?.version, change_note: form.change_note },
          });
    },
    onSuccess: (tc) => {
      void qc.invalidateQueries({ queryKey: ["test-cases"] });
      void qc.invalidateQueries({ queryKey: ["test-case-versions", tc.id] });
      qc.setQueryData(["test-case", tc.id], tc);
      toast.success(isNew ? `Đã tạo ${tc.code}` : `Đã lưu ${tc.code} (phiên bản ${tc.version})`);
      if (isNew) navigate(`/test-cases/${tc.id}`, { replace: true });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) toast.error(`${e.message}. Hãy tải lại để xem thay đổi mới nhất.`);
      else toast.error(e.message);
    },
  });
  const duplicate = useMutation({
    mutationFn: () => api<TestCase>(`/api/test-cases/${caseId}/duplicate`, { method: "POST" }),
    onSuccess: (tc) => {
      void qc.invalidateQueries({ queryKey: ["test-cases"] });
      toast.success(`Đã tạo bản sao ${tc.code}`);
      navigate(`/test-cases/${tc.id}`);
    },
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: () => api<void>(`/api/test-cases/${caseId}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["test-cases"] });
      void qc.invalidateQueries({ queryKey: ["test-case", caseId] });
      toast.success("Đã xóa test case (có thể khôi phục)");
      setConfirmDelete(false);
    },
    onError: (e) => toast.error(e.message),
  });
  const restore = useMutation({
    mutationFn: () => api<TestCase>(`/api/test-cases/${caseId}/restore`, { method: "POST" }),
    onSuccess: (tc) => {
      qc.setQueryData(["test-case", tc.id], tc);
      void qc.invalidateQueries({ queryKey: ["test-cases"] });
      toast.success("Đã khôi phục test case");
    },
    onError: (e) => toast.error(e.message),
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) {
      toast.error("Vui lòng nhập tiêu đề");
      return;
    }
    if (hasInvalidJson(form.definition)) {
      toast.error("Còn ô JSON không hợp lệ trong các bước. Hãy sửa trước khi lưu.");
      return;
    }
    save.mutate();
  };

  return (
    <>
      <PageHeader
        breadcrumb={
          <Link to={`/test-cases?project=${projectId ?? ""}`} className="hover:underline">
            Test case {project ? `· ${project.key}` : ""}
          </Link>
        }
        title={isNew ? "Tạo test case" : `${tc?.code} · ${tc?.title}`}
        description={
          tc && (
            <span className="flex flex-wrap items-center gap-2">
              Phiên bản {tc.version} · cập nhật {formatDateTime(tc.updated_at)}
              {tc.is_deleted && <Badge variant="danger">Đã xóa</Badge>}
              {tc.side_effect && <Badge variant="warning">Thay đổi dữ liệu</Badge>}
            </span>
          )
        }
        actions={
          tc && (
            <>
              {can(role, "tester") && !tc.is_deleted && !project?.is_archived && (
                <Button variant="outline" onClick={() => setRunOpen(true)}>
                  <Play /> Chạy
                </Button>
              )}
              {canEdit && (
                <>
                  <Button variant="outline" loading={duplicate.isPending} onClick={() => duplicate.mutate()}>
                    <Copy /> Nhân bản
                  </Button>
                  <Button variant="outline" onClick={() => setConfirmDelete(true)}>
                    <Trash2 /> Xóa
                  </Button>
                </>
              )}
              {tc.is_deleted && can(role, "manager") && (
                <Button loading={restore.isPending} onClick={() => restore.mutate()}>
                  <ArchiveRestore /> Khôi phục
                </Button>
              )}
            </>
          )
        }
      />

      <form onSubmit={submit} noValidate className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <fieldset disabled={!isNew && !canEdit} className="grid min-w-0 grid-cols-1 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Thông tin</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4">
              <FormField id="tc-title" label="Tiêu đề" required>
                <Input id="tc-title" value={form.title} maxLength={300} onChange={(e) => set("title", e.target.value)} />
              </FormField>
              <div className="grid gap-4 sm:grid-cols-3">
                <FormField id="tc-type" label="Loại test" hint={!isNew ? "Đổi loại sẽ tạo lại các bước" : undefined}>
                  <NativeSelect
                    id="tc-type"
                    value={form.test_type}
                    onChange={(e) => {
                      const t = e.target.value as TestType;
                      setForm((f) => ({ ...f, test_type: t, definition: defaultDefinition(t) }));
                      setFormKey((k) => k + 1);
                    }}
                  >
                    {Object.entries(TEST_TYPE_LABEL).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </NativeSelect>
                </FormField>
                <FormField id="tc-priority" label="Mức ưu tiên">
                  <NativeSelect id="tc-priority" value={form.priority} onChange={(e) => set("priority", e.target.value as Priority)}>
                    {Object.entries(PRIORITY_LABEL).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </NativeSelect>
                </FormField>
                <FormField id="tc-status" label="Trạng thái">
                  <NativeSelect id="tc-status" value={form.status} onChange={(e) => set("status", e.target.value as TestCaseStatus)}>
                    {Object.entries(CASE_STATUS_LABEL).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </NativeSelect>
                </FormField>
              </div>
              <FormField id="tc-tags" label="Nhãn" hint="Cách nhau bằng dấu phẩy, VD smoke, login">
                <Input id="tc-tags" value={form.tags} onChange={(e) => set("tags", e.target.value)} />
              </FormField>
              <FormField id="tc-desc" label="Mô tả">
                <Textarea id="tc-desc" value={form.description} onChange={(e) => set("description", e.target.value)} />
              </FormField>
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField id="tc-pre" label="Điều kiện trước">
                  <Textarea id="tc-pre" value={form.preconditions} onChange={(e) => set("preconditions", e.target.value)} />
                </FormField>
                <FormField id="tc-exp" label="Kết quả mong đợi">
                  <Textarea id="tc-exp" value={form.expected_result} onChange={(e) => set("expected_result", e.target.value)} />
                </FormField>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Các bước</CardTitle>
              <CardDescription>
                Dùng {"{{TEN_BIEN}}"} để lấy biến của môi trường hoặc giá trị lấy ở bước trước. Secret được che trong mọi log và kết quả.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <DefinitionEditor key={formKey} value={form.definition} onChange={(d) => set("definition", d)} />
            </CardContent>
          </Card>
        </fieldset>

        <div className="grid content-start gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Thực thi</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4">
              <fieldset disabled={!isNew && !canEdit} className="grid gap-4">
                <label className="flex items-start gap-3 text-sm">
                  <Switch checked={form.side_effect} onCheckedChange={(v) => set("side_effect", v)} aria-label="Có thay đổi dữ liệu" />
                  <span>
                    Có thay đổi dữ liệu trên hệ thống đích
                    <span className="block text-xs text-muted-foreground">
                      Test API có POST, PUT, PATCH, DELETE luôn được tính là thay đổi dữ liệu. Test loại này không tự thử lại và cần xác nhận khi chạy.
                    </span>
                  </span>
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <FormField id="tc-retry" label="Thử lại khi lỗi">
                    <NativeSelect id="tc-retry" value={form.retry_count} onChange={(e) => set("retry_count", Number(e.target.value))}>
                      {[0, 1, 2, 3].map((n) => (
                        <option key={n} value={n}>{n} lần</option>
                      ))}
                    </NativeSelect>
                  </FormField>
                  <FormField id="tc-timeout" label="Tối đa (giây)">
                    <Input id="tc-timeout" type="number" min={5} max={3600} value={form.timeout_seconds} onChange={(e) => set("timeout_seconds", Number(e.target.value))} />
                  </FormField>
                </div>
                {!isNew && (
                  <FormField id="tc-note" label="Ghi chú thay đổi">
                    <Input id="tc-note" maxLength={500} placeholder="VD sửa URL đăng nhập" value={form.change_note} onChange={(e) => set("change_note", e.target.value)} />
                  </FormField>
                )}
              </fieldset>
              {(isNew || canEdit) && (
                <Button type="submit" loading={save.isPending}>
                  <Save /> {isNew ? "Tạo test case" : "Lưu thay đổi"}
                </Button>
              )}
              {!isNew && !canEdit && (
                <p className="text-xs text-muted-foreground">
                  {tc?.is_deleted ? "Test case đã xóa, khôi phục để sửa." : "Bạn chỉ có quyền xem test case này."}
                </p>
              )}
            </CardContent>
          </Card>
          {!isNew && caseId && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <History className="size-4" /> Lịch sử phiên bản
                </CardTitle>
              </CardHeader>
              <CardContent>
                <VersionsPanel caseId={caseId} />
              </CardContent>
            </Card>
          )}
        </div>
      </form>

      {tc && (
        <>
          <ConfirmDialog
            open={confirmDelete}
            onOpenChange={setConfirmDelete}
            title={`Xóa ${tc.code}?`}
            description="Test case bị ẩn khỏi danh sách và gỡ khỏi các suite. Kết quả chạy cũ vẫn giữ nguyên, có thể khôi phục sau."
            confirmLabel="Xóa"
            loading={remove.isPending}
            onConfirm={() => remove.mutate()}
          />
          <RunDialog open={runOpen} onOpenChange={setRunOpen} projectId={tc.project_id} testCaseIds={[tc.id]} label={`${tc.code} · ${tc.title}`} />
        </>
      )}
    </>
  );
}
