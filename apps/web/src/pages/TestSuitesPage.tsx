import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  Layers,
  Play,
  Plus,
  Save,
  Trash2,
  X,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { FormField } from "@/components/form-field";
import { PageHeader } from "@/components/page-header";
import { ProjectPicker } from "@/components/project-picker";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { RunDialog } from "@/features/run-dialog";
import { useProjectSelection } from "@/hooks/projects";
import { useDebounced } from "@/hooks/use-debounced";
import {
  api,
  can,
  type Page,
  type Project,
  type Suite,
  type SuiteDetail,
  type TestCase,
} from "@/lib/api";
import { TEST_TYPE_LABEL } from "@/lib/test-labels";
import { formatDateTime } from "@/lib/utils";

type SuiteFormProps = {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  projectId: string;
  suite?: SuiteDetail;
};

function SuiteFormDialog(props: SuiteFormProps) {
  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent>
        <SuiteFormBody {...props} />
      </DialogContent>
    </Dialog>
  );
}

function SuiteFormBody({ onOpenChange, projectId, suite }: SuiteFormProps) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState(suite?.name ?? "");
  const [description, setDescription] = useState(suite?.description ?? "");
  const m = useMutation({
    mutationFn: () =>
      suite
        ? api<SuiteDetail>(`/api/suites/${suite.id}`, {
            method: "PATCH",
            json: { name, description },
          })
        : api<SuiteDetail>(`/api/projects/${projectId}/suites`, {
            method: "POST",
            json: { name, description },
          }),
    onSuccess: (s) => {
      void qc.invalidateQueries({ queryKey: ["suites"] });
      qc.setQueryData(["suite", s.id], s);
      toast.success(suite ? "Đã lưu suite" : `Đã tạo suite ${s.name}`);
      onOpenChange(false);
      if (!suite) navigate(`/test-suites/${s.id}`);
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <>
      <DialogHeader>
        <DialogTitle>{suite ? "Sửa suite" : "Tạo suite"}</DialogTitle>
      </DialogHeader>
      <form
        className="grid gap-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          if (!name.trim()) return toast.error("Vui lòng nhập tên suite");
          m.mutate();
        }}
      >
        <FormField id="s-name" label="Tên" required>
          <Input
            id="s-name"
            maxLength={200}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </FormField>
        <FormField id="s-desc" label="Mô tả">
          <Textarea
            id="s-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </FormField>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Hủy
          </Button>
          <Button type="submit" loading={m.isPending}>
            Lưu
          </Button>
        </DialogFooter>
      </form>
    </>
  );
}

export function TestSuitesPage() {
  const { query: pq, projects, selected, select } = useProjectSelection();
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["suites", selected?.id],
    enabled: !!selected,
    queryFn: () => api<Suite[]>(`/api/projects/${selected?.id}/suites`),
  });
  const canManage = can(selected?.my_role, "manager") && !selected?.is_archived;
  return (
    <>
      <PageHeader
        title="Test suite"
        description="Nhóm test case theo mục đích (smoke, hồi quy...) để chạy cùng nhau."
        actions={
          canManage && (
            <Button onClick={() => setOpen(true)}>
              <Plus /> Tạo suite
            </Button>
          )
        }
      />
      {pq.isPending && <LoadingState />}
      {pq.isError && (
        <ErrorState message={pq.error.message} onRetry={() => pq.refetch()} />
      )}
      {pq.data && projects.length === 0 && <EmptyState title="Chưa có dự án" />}
      {selected && (
        <Card>
          <CardContent className="space-y-4 p-4 sm:p-5">
            <div className="max-w-sm">
              <ProjectPicker
                id="suite-project"
                projects={projects}
                value={selected.id}
                onChange={select}
              />
            </div>
            {q.isPending && <LoadingState />}
            {q.isError && (
              <ErrorState
                message={q.error.message}
                onRetry={() => q.refetch()}
              />
            )}
            {q.data &&
              (q.data.length === 0 ? (
                <EmptyState
                  icon={<Layers className="size-6" />}
                  title="Chưa có suite"
                  description="Tạo suite rồi thêm test case vào để chạy theo nhóm."
                />
              ) : (
                <Table>
                  <THead>
                    <TR>
                      <TH>Tên</TH>
                      <TH>Số test case</TH>
                      <TH className="hidden md:table-cell">Cập nhật</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {q.data.map((s) => (
                      <TR key={s.id}>
                        <TD>
                          <Link
                            to={`/test-suites/${s.id}`}
                            className="font-medium hover:underline"
                          >
                            {s.name}
                          </Link>
                          {s.description && (
                            <p className="text-xs text-muted-foreground">
                              {s.description}
                            </p>
                          )}
                        </TD>
                        <TD className="tabular-nums">{s.case_count}</TD>
                        <TD className="hidden text-muted-foreground md:table-cell">
                          {formatDateTime(s.updated_at)}
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              ))}
          </CardContent>
        </Card>
      )}
      {selected && (
        <SuiteFormDialog
          open={open}
          onOpenChange={setOpen}
          projectId={selected.id}
        />
      )}
    </>
  );
}

type AddCasesProps = {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  projectId: string;
  existing: Set<string>;
  onAdd: (cases: TestCase[]) => void;
};

function AddCasesDialog(props: AddCasesProps) {
  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className="max-w-2xl">
        <AddCasesBody {...props} />
      </DialogContent>
    </Dialog>
  );
}

function AddCasesBody({
  onOpenChange,
  projectId,
  existing,
  onAdd,
}: AddCasesProps) {
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());
  const [picked, setPicked] = useState<Map<string, TestCase>>(new Map());
  const list = useQuery({
    queryKey: ["test-cases", projectId, "picker", q],
    queryFn: () =>
      api<Page<TestCase>>(
        `/api/projects/${projectId}/test-cases?page_size=100${q ? `&q=${encodeURIComponent(q)}` : ""}`,
      ),
  });
  const items = (list.data?.items ?? []).filter((tc) => !existing.has(tc.id));
  return (
    <>
      <DialogHeader>
        <DialogTitle>Thêm test case vào suite</DialogTitle>
        <DialogDescription>
          Hiện tối đa 100 kết quả, hãy tìm theo mã hoặc tiêu đề.
        </DialogDescription>
      </DialogHeader>
      <Input
        aria-label="Tìm test case"
        placeholder="Tìm theo mã hoặc tiêu đề"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <div className="max-h-80 overflow-y-auto rounded-md border">
        {list.isPending && <LoadingState rows={3} />}
        {list.data && items.length === 0 && (
          <p className="p-4 text-center text-sm text-muted-foreground">
            Không còn test case nào để thêm.
          </p>
        )}
        <ul className="divide-y">
          {items.map((tc) => (
            <li key={tc.id}>
              <label className="flex cursor-pointer items-center gap-3 px-3 py-2 text-sm hover:bg-muted">
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={picked.has(tc.id)}
                  onChange={() =>
                    setPicked((m) => {
                      const n = new Map(m);
                      if (n.has(tc.id)) n.delete(tc.id);
                      else n.set(tc.id, tc);
                      return n;
                    })
                  }
                />
                <span className="font-mono text-xs">{tc.code}</span>
                <span className="min-w-0 flex-1 truncate">{tc.title}</span>
                <Badge variant="outline">{TEST_TYPE_LABEL[tc.test_type]}</Badge>
              </label>
            </li>
          ))}
        </ul>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          Hủy
        </Button>
        <Button
          disabled={picked.size === 0}
          onClick={() => {
            onAdd([...picked.values()]);
            onOpenChange(false);
          }}
        >
          Thêm {picked.size} test case
        </Button>
      </DialogFooter>
    </>
  );
}

export function SuiteDetailPage() {
  const { suiteId = "" } = useParams();
  const q = useQuery({
    queryKey: ["suite", suiteId],
    queryFn: () => api<SuiteDetail>(`/api/suites/${suiteId}`),
  });
  const pq = useQuery({
    queryKey: ["project", q.data?.project_id],
    enabled: !!q.data,
    queryFn: () => api<Project>(`/api/projects/${q.data?.project_id}`),
  });
  if (q.isPending) return <LoadingState rows={5} />;
  if (q.isError)
    return <ErrorState message={q.error.message} onRetry={() => q.refetch()} />;
  // Dựng lại trình sửa khi dữ liệu máy chủ đổi (sau khi lưu), để danh sách cục bộ khớp bản mới.
  return (
    <SuiteEditor
      key={`${q.data.id}-${q.data.updated_at}-${q.data.case_count}`}
      suite={q.data}
      project={pq.data}
    />
  );
}

function SuiteEditor({
  suite,
  project,
}: {
  suite: SuiteDetail;
  project: Project | undefined;
}) {
  const suiteId = suite.id;
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [cases, setCases] = useState<TestCase[]>(() =>
    (suite.items ?? []).map((i) => i.test_case),
  );
  const [dirty, setDirty] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [runOpen, setRunOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const update = (next: TestCase[]) => {
    setCases(next);
    setDirty(true);
  };
  const saveItems = useMutation({
    mutationFn: () =>
      api<SuiteDetail>(`/api/suites/${suiteId}/items`, {
        method: "PUT",
        json: { test_case_ids: cases.map((c) => c.id) },
      }),
    onSuccess: (s) => {
      setDirty(false);
      qc.setQueryData(["suite", s.id], s);
      void qc.invalidateQueries({ queryKey: ["suites"] });
      toast.success("Đã lưu danh sách test case của suite");
    },
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: () => api<void>(`/api/suites/${suiteId}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["suites"] });
      toast.success("Đã xóa suite");
      navigate(`/test-suites?project=${suite.project_id}`);
    },
    onError: (e) => toast.error(e.message),
  });

  const role = project?.my_role;
  const canManage = can(role, "manager") && !project?.is_archived;
  const move = (i: number, d: number) => {
    const j = i + d;
    if (j < 0 || j >= cases.length) return;
    const n = [...cases];
    [n[i], n[j]] = [n[j], n[i]];
    update(n);
  };

  return (
    <>
      <PageHeader
        breadcrumb={
          <Link
            to={`/test-suites?project=${suite.project_id}`}
            className="hover:underline"
          >
            Test suite {project ? `· ${project.key}` : ""}
          </Link>
        }
        title={suite.name}
        description={suite.description || "Chưa có mô tả"}
        actions={
          <>
            {can(role, "tester") && !project?.is_archived && (
              <Button
                disabled={suite.case_count === 0 || dirty}
                title={dirty ? "Lưu thay đổi trước khi chạy" : undefined}
                onClick={() => setRunOpen(true)}
              >
                <Play /> Chạy suite
              </Button>
            )}
            {canManage && (
              <>
                <Button variant="outline" onClick={() => setEditOpen(true)}>
                  Sửa
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setConfirmDelete(true)}
                >
                  <Trash2 /> Xóa
                </Button>
              </>
            )}
          </>
        }
      />
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
          <CardTitle>{cases.length} test case</CardTitle>
          {canManage && (
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setAddOpen(true)}
              >
                <Plus /> Thêm test case
              </Button>
              <Button
                size="sm"
                disabled={!dirty}
                loading={saveItems.isPending}
                onClick={() => saveItems.mutate()}
              >
                <Save /> Lưu thứ tự
              </Button>
            </div>
          )}
        </CardHeader>
        <CardContent>
          {cases.length === 0 ? (
            <EmptyState
              title="Suite chưa có test case"
              description={
                canManage ? "Bấm Thêm test case để chọn." : undefined
              }
            />
          ) : (
            <ol className="divide-y rounded-md border">
              {cases.map((tc, i) => (
                <li
                  key={tc.id}
                  className="flex items-center gap-3 px-3 py-2 text-sm"
                >
                  <span className="w-6 text-right tabular-nums text-muted-foreground">
                    {i + 1}
                  </span>
                  <span className="font-mono text-xs">{tc.code}</span>
                  <Link
                    to={`/test-cases/${tc.id}`}
                    className="min-w-0 flex-1 truncate hover:underline"
                  >
                    {tc.title}
                  </Link>
                  <Badge variant="outline" className="hidden sm:inline-flex">
                    {TEST_TYPE_LABEL[tc.test_type]}
                  </Badge>
                  {tc.side_effect && (
                    <Badge variant="warning" className="hidden sm:inline-flex">
                      Thay đổi dữ liệu
                    </Badge>
                  )}
                  {canManage && (
                    <span className="flex">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Đưa ${tc.code} lên`}
                        disabled={i === 0}
                        onClick={() => move(i, -1)}
                      >
                        <ArrowUp />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Đưa ${tc.code} xuống`}
                        disabled={i === cases.length - 1}
                        onClick={() => move(i, 1)}
                      >
                        <ArrowDown />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Bỏ ${tc.code} khỏi suite`}
                        onClick={() =>
                          update(cases.filter((c) => c.id !== tc.id))
                        }
                      >
                        <X />
                      </Button>
                    </span>
                  )}
                </li>
              ))}
            </ol>
          )}
          {dirty && (
            <p className="mt-3 text-sm text-status-blocked">
              Có thay đổi chưa lưu.
            </p>
          )}
        </CardContent>
      </Card>
      <SuiteFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        projectId={suite.project_id}
        suite={suite}
      />
      <AddCasesDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        projectId={suite.project_id}
        existing={new Set(cases.map((c) => c.id))}
        onAdd={(added) => update([...cases, ...added])}
      />
      <RunDialog
        open={runOpen}
        onOpenChange={setRunOpen}
        projectId={suite.project_id}
        suiteId={suite.id}
        label={`Suite ${suite.name} (${suite.case_count} test case)`}
      />
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Xóa suite ${suite.name}?`}
        description="Chỉ xóa nhóm, không xóa test case. Lịch sử chạy của suite vẫn được giữ."
        confirmLabel="Xóa suite"
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </>
  );
}
