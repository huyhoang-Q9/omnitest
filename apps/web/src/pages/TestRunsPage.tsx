import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { PlayCircle } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/page-header";
import { ProjectPicker } from "@/components/project-picker";
import { Pagination } from "@/components/pagination";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { RunProgress } from "@/features/runs";
import { useProjectSelection } from "@/hooks/projects";
import { api, type Page, type Run } from "@/lib/api";
import { STATUS_META, type RunStatus } from "@/lib/status";
import { formatDuration } from "@/lib/test-labels";
import { formatDateTime } from "@/lib/utils";

const PAGE_SIZE = 20;

export function TestRunsPage() {
  const { query: pq, projects, selected, select } = useProjectSelection();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const page = Number(params.get("page") ?? 1);
  const q = useQuery({
    queryKey: ["runs", selected?.id, status, page],
    enabled: !!selected,
    placeholderData: keepPreviousData,
    queryFn: () =>
      api<Page<Run>>(`/api/projects/${selected?.id}/runs?page=${page}&page_size=${PAGE_SIZE}${status ? `&status=${status}` : ""}`),
    // Tự làm mới khi còn lần chạy chưa kết thúc.
    refetchInterval: (query) => (query.state.data?.items.some((r) => r.status === "queued" || r.status === "running") ? 3000 : false),
  });
  const setParam = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    if (k !== "page") next.delete("page");
    setParams(next, { replace: k !== "page" });
  };
  return (
    <>
      <PageHeader title="Lần chạy" description="Lịch sử chạy test theo dự án, kết quả từng test case và từng bước." />
      {pq.isPending && <LoadingState />}
      {pq.isError && <ErrorState message={pq.error.message} onRetry={() => pq.refetch()} />}
      {pq.data && projects.length === 0 && <EmptyState title="Chưa có dự án" />}
      {selected && (
        <Card>
          <CardContent className="space-y-4 p-4 sm:p-5">
            <div className="grid gap-3 sm:grid-cols-2 lg:max-w-2xl">
              <ProjectPicker id="run-project" projects={projects} value={selected.id} onChange={select} />
              <div className="grid gap-1.5">
                <Label htmlFor="run-status">Trạng thái</Label>
                <NativeSelect id="run-status" value={status} onChange={(e) => setParam("status", e.target.value)}>
                  <option value="">Tất cả</option>
                  {(Object.keys(STATUS_META) as RunStatus[]).map((s) => (
                    <option key={s} value={s}>
                      {STATUS_META[s].label}
                    </option>
                  ))}
                </NativeSelect>
              </div>
            </div>
            {q.isPending && <LoadingState />}
            {q.isError && <ErrorState message={q.error.message} onRetry={() => q.refetch()} />}
            {q.data &&
              (q.data.items.length === 0 ? (
                <EmptyState
                  icon={<PlayCircle className="size-6" />}
                  title="Chưa có lần chạy"
                  description="Chọn test case hoặc suite rồi bấm Chạy để bắt đầu."
                />
              ) : (
                <>
                  <Table>
                    <THead>
                      <TR>
                        <TH>Lần chạy</TH>
                        <TH>Trạng thái</TH>
                        <TH className="hidden md:table-cell">Kết quả</TH>
                        <TH className="hidden lg:table-cell">Môi trường</TH>
                        <TH className="hidden lg:table-cell">Thời lượng</TH>
                      </TR>
                    </THead>
                    <TBody>
                      {q.data.items.map((r) => (
                        <TR key={r.id}>
                          <TD>
                            <Link to={`/test-runs/${r.id}`} className="font-medium hover:underline">
                              {r.title}
                            </Link>
                            <p className="text-xs text-muted-foreground">
                              {formatDateTime(r.created_at)} · {r.triggered_by_email ?? "Hệ thống"}
                            </p>
                          </TD>
                          <TD>
                            <StatusBadge status={r.status} />
                          </TD>
                          <TD className="hidden min-w-48 md:table-cell">
                            <RunProgress run={r} />
                          </TD>
                          <TD className="hidden lg:table-cell">{r.environment_name}</TD>
                          <TD className="hidden whitespace-nowrap lg:table-cell">{formatDuration(r.duration_ms)}</TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                  <Pagination page={page} pageSize={PAGE_SIZE} total={q.data.total} onPageChange={(p) => setParam("page", String(p))} />
                </>
              ))}
          </CardContent>
        </Card>
      )}
    </>
  );
}
