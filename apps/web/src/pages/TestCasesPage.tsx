import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileCode, ListChecks, Play, Plus, Search, Upload } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { ProjectPicker } from "@/components/project-picker";
import { Pagination } from "@/components/pagination";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, NativeSelect } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { OpenApiImportDialog } from "@/features/openapi-import";
import { RunDialog } from "@/features/run-dialog";
import { useProjectSelection } from "@/hooks/projects";
import { useDebounced } from "@/hooks/use-debounced";
import { api, can, type ImportResult, type Page, type TestCase } from "@/lib/api";
import { CASE_STATUS_LABEL, PRIORITY_LABEL, RUNNABLE_TYPES, TEST_TYPE_LABEL } from "@/lib/test-labels";
import { formatDateTime } from "@/lib/utils";

const PAGE_SIZE = 20;

function ImportDialog({ projectId, open, onOpenChange }: { projectId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const send = (dryRun: boolean) => {
    const body = new FormData();
    body.append("file", file as File);
    return api<ImportResult>(`/api/projects/${projectId}/test-cases/import?dry_run=${dryRun}`, { method: "POST", body });
  };
  const check = useMutation({ mutationFn: () => send(true), onSuccess: setPreview, onError: (e) => toast.error(e.message) });
  const apply = useMutation({
    mutationFn: () => send(false),
    onSuccess: (r) => {
      toast.success(`Đã nhập: ${r.created} tạo mới, ${r.updated} cập nhật`);
      void qc.invalidateQueries({ queryKey: ["test-cases"] });
      onOpenChange(false);
    },
    onError: (e) => toast.error(e.message),
  });
  const reset = (o: boolean) => {
    if (!o) {
      setFile(null);
      setPreview(null);
    }
    onOpenChange(o);
  };
  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Nhập test case từ CSV/Excel</DialogTitle>
          <DialogDescription>
            Dùng đúng mẫu cột của file xuất ra. Hệ thống kiểm tra toàn bộ trước; chỉ khi không có dòng lỗi mới được nhập (tất cả hoặc không).
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-1.5">
          <Label htmlFor="import-file">File (.csv hoặc .xlsx, tối đa 2 MB)</Label>
          <Input
            id="import-file"
            type="file"
            accept=".csv,.xlsx"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setPreview(null);
            }}
          />
        </div>
        {preview && (
          <div className="grid gap-2 rounded-md border p-3 text-sm" role="status">
            <p>
              {preview.total_rows} dòng: {preview.created} tạo mới, {preview.updated} cập nhật, {preview.errors.length} lỗi.
            </p>
            {preview.errors.length > 0 && (
              <ul className="max-h-48 list-disc space-y-1 overflow-y-auto pl-5 text-status-failed">
                {preview.errors.map((e, i) => (
                  <li key={i}>
                    Dòng {e.row}: {e.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => reset(false)}>
            Hủy
          </Button>
          {!preview ? (
            <Button disabled={!file} loading={check.isPending} onClick={() => check.mutate()}>
              Kiểm tra file
            </Button>
          ) : (
            <Button
              disabled={preview.errors.length > 0 || preview.total_rows === 0}
              loading={apply.isPending}
              onClick={() => apply.mutate()}
            >
              Nhập {preview.created + preview.updated} test case
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function TestCasesPage() {
  const { query: pq, projects, selected, select } = useProjectSelection();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const q = useDebounced(search.trim());
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [importOpen, setImportOpen] = useState(false);
  const [openApiOpen, setOpenApiOpen] = useState(false);
  const [runOpen, setRunOpen] = useState(false);
  const page = Number(params.get("page") ?? 1);
  const filters = {
    test_type: params.get("type") ?? "",
    priority: params.get("priority") ?? "",
    status: params.get("status") ?? "",
    include_deleted: params.get("deleted") === "1",
  };
  const setParam = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    next.delete("page");
    setParams(next, { replace: true });
  };

  const pid = selected?.id;
  const list = useQuery({
    queryKey: ["test-cases", pid, q, filters, page],
    enabled: !!pid,
    placeholderData: keepPreviousData,
    queryFn: () => {
      const sp = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
      if (q) sp.set("q", q);
      if (filters.test_type) sp.set("test_type", filters.test_type);
      if (filters.priority) sp.set("priority", filters.priority);
      if (filters.status) sp.set("status", filters.status);
      if (filters.include_deleted) sp.set("include_deleted", "true");
      return api<Page<TestCase>>(`/api/projects/${pid}/test-cases?${sp}`);
    },
  });
  const role = selected?.my_role;
  const writable = !selected?.is_archived;
  const items = list.data?.items ?? [];
  const toggle = (id: string) =>
    setSelectedIds((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const runnable = items.filter((i) => !i.is_deleted);

  return (
    <>
      <PageHeader
        title="Test case"
        description="Test API và Web dạng khai báo từng bước; test Desktop/Mobile lưu được nhưng chưa chạy thật."
        actions={
          selected && (
            <>
              <Button variant="outline" asChild>
                <a href={`/api/projects/${selected.id}/test-cases/export?format=xlsx`}>
                  <Download /> Excel
                </a>
              </Button>
              <Button variant="outline" asChild>
                <a href={`/api/projects/${selected.id}/test-cases/export?format=csv`}>
                  <Download /> CSV
                </a>
              </Button>
              {can(role, "manager") && writable && (
                <>
                  <Button variant="outline" onClick={() => setImportOpen(true)}>
                    <Upload /> Nhập
                  </Button>
                  <Button variant="outline" onClick={() => setOpenApiOpen(true)}>
                    <FileCode /> Từ OpenAPI
                  </Button>
                  <Button asChild>
                    <Link to={`/test-cases/new?project=${selected.id}`}>
                      <Plus /> Tạo test case
                    </Link>
                  </Button>
                </>
              )}
            </>
          )
        }
      />
      {pq.isPending && <LoadingState />}
      {pq.isError && <ErrorState message={pq.error.message} onRetry={() => pq.refetch()} />}
      {pq.data && projects.length === 0 && <EmptyState title="Chưa có dự án" description="Test case thuộc về dự án. Hãy tạo hoặc được thêm vào một dự án trước." />}
      {selected && (
        <Card>
          <CardContent className="space-y-4 p-4 sm:p-5">
            <div className="grid gap-3 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1.5fr)_repeat(3,minmax(0,1fr))]">
              <ProjectPicker id="tc-project" projects={projects} value={selected.id} onChange={(id) => { setSelectedIds(new Set()); select(id); }} />
              <div className="grid gap-1.5">
                <Label htmlFor="tc-search">Tìm kiếm</Label>
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
                  <Input id="tc-search" className="pl-8" placeholder="Mã hoặc tiêu đề" value={search} onChange={(e) => { setSearch(e.target.value); setParam("q", e.target.value.trim()); }} />
                </div>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="tc-type">Loại</Label>
                <NativeSelect id="tc-type" value={filters.test_type} onChange={(e) => setParam("type", e.target.value)}>
                  <option value="">Tất cả</option>
                  {Object.entries(TEST_TYPE_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </NativeSelect>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="tc-priority">Mức ưu tiên</Label>
                <NativeSelect id="tc-priority" value={filters.priority} onChange={(e) => setParam("priority", e.target.value)}>
                  <option value="">Tất cả</option>
                  {Object.entries(PRIORITY_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </NativeSelect>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="tc-status">Trạng thái</Label>
                <NativeSelect id="tc-status" value={filters.status} onChange={(e) => setParam("status", e.target.value)}>
                  <option value="">Tất cả</option>
                  {Object.entries(CASE_STATUS_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </NativeSelect>
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <label className="flex items-center gap-2 text-sm">
                <Switch checked={filters.include_deleted} onCheckedChange={(v) => setParam("deleted", v ? "1" : "")} aria-label="Hiện test case đã xóa" />
                Hiện test case đã xóa
              </label>
              {can(role, "tester") && writable && (
                <Button size="sm" disabled={selectedIds.size === 0} onClick={() => setRunOpen(true)}>
                  <Play /> Chạy {selectedIds.size > 0 ? `${selectedIds.size} test đã chọn` : "test đã chọn"}
                </Button>
              )}
            </div>

            {list.isPending && <LoadingState />}
            {list.isError && <ErrorState message={list.error.message} onRetry={() => list.refetch()} />}
            {list.data &&
              (items.length === 0 ? (
                <EmptyState
                  icon={<ListChecks className="size-6" />}
                  title={q || filters.test_type || filters.priority || filters.status ? "Không có test case phù hợp" : "Chưa có test case"}
                  description="Tạo test case mới, nhập từ file hoặc chạy lệnh seed-demo để có bộ test mẫu."
                />
              ) : (
                <>
                  <Table>
                    <THead>
                      <TR>
                        <TH className="w-10">
                          <input
                            type="checkbox"
                            aria-label="Chọn tất cả trên trang"
                            className="size-4 accent-primary"
                            checked={runnable.length > 0 && runnable.every((i) => selectedIds.has(i.id))}
                            onChange={(e) =>
                              setSelectedIds((s) => {
                                const n = new Set(s);
                                runnable.forEach((i) => (e.target.checked ? n.add(i.id) : n.delete(i.id)));
                                return n;
                              })
                            }
                          />
                        </TH>
                        <TH>Mã</TH>
                        <TH>Tiêu đề</TH>
                        <TH className="hidden md:table-cell">Loại</TH>
                        <TH className="hidden lg:table-cell">Ưu tiên</TH>
                        <TH className="hidden lg:table-cell">Trạng thái</TH>
                        <TH className="hidden xl:table-cell">Cập nhật</TH>
                      </TR>
                    </THead>
                    <TBody>
                      {items.map((tc) => (
                        <TR key={tc.id} className={tc.is_deleted ? "opacity-60" : undefined}>
                          <TD>
                            <input
                              type="checkbox"
                              aria-label={`Chọn ${tc.code}`}
                              className="size-4 accent-primary"
                              disabled={tc.is_deleted}
                              checked={selectedIds.has(tc.id)}
                              onChange={() => toggle(tc.id)}
                            />
                          </TD>
                          <TD className="whitespace-nowrap font-mono text-xs">{tc.code}</TD>
                          <TD>
                            <Link to={`/test-cases/${tc.id}`} className="font-medium hover:underline">
                              {tc.title}
                            </Link>
                            <div className="mt-1 flex flex-wrap gap-1">
                              {tc.is_deleted && <Badge variant="danger">Đã xóa</Badge>}
                              {tc.side_effect && <Badge variant="warning">Thay đổi dữ liệu</Badge>}
                              {!RUNNABLE_TYPES.includes(tc.test_type) && (
                                <Badge variant="muted">{tc.step_count === 0 ? "Chưa có bước tự động" : "Thử nghiệm (Appium)"}</Badge>
                              )}
                              {tc.tags.map((t) => (
                                <Badge key={t} variant="outline">{t}</Badge>
                              ))}
                            </div>
                          </TD>
                          <TD className="hidden md:table-cell">
                            {TEST_TYPE_LABEL[tc.test_type]} · {tc.step_count} bước
                          </TD>
                          <TD className="hidden lg:table-cell">{PRIORITY_LABEL[tc.priority]}</TD>
                          <TD className="hidden lg:table-cell">{CASE_STATUS_LABEL[tc.status]}</TD>
                          <TD className="hidden whitespace-nowrap text-muted-foreground xl:table-cell">
                            {formatDateTime(tc.updated_at)} · v{tc.version}
                          </TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                  <Pagination
                    page={page}
                    pageSize={PAGE_SIZE}
                    total={list.data.total}
                    onPageChange={(p) => {
                      const next = new URLSearchParams(params);
                      next.set("page", String(p));
                      setParams(next);
                    }}
                  />
                </>
              ))}
          </CardContent>
        </Card>
      )}
      {selected && <ImportDialog projectId={selected.id} open={importOpen} onOpenChange={setImportOpen} />}
      {selected && <OpenApiImportDialog projectId={selected.id} open={openApiOpen} onOpenChange={setOpenApiOpen} />}
      {selected && (
        <RunDialog
          open={runOpen}
          onOpenChange={setRunOpen}
          projectId={selected.id}
          testCaseIds={[...selectedIds]}
          label={`${selectedIds.size} test case đã chọn trong dự án ${selected.key}`}
        />
      )}
    </>
  );
}
