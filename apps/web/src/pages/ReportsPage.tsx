import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { BarChart3, Download, FileText } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PageHeader } from "@/components/page-header";
import { ProjectPicker } from "@/components/project-picker";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useProjectSelection } from "@/hooks/projects";
import { api, type Environment, type ProjectReport, type ReportGroup, type Suite } from "@/lib/api";
import { formatPassRate, reportQuery } from "@/lib/report";
import { formatDateTime } from "@/lib/utils";

const CASE_LIMIT = 50;

function Stat({ label, value, note }: { label: string; value: string | number; note?: string }) {
  return (
    <Card>
      <CardContent className="space-y-1 p-4">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="text-2xl font-semibold tabular-nums">{value}</p>
        {note && <p className="text-xs text-muted-foreground">{note}</p>}
      </CardContent>
    </Card>
  );
}

function GroupTable({ title, rows, empty }: { title: string; rows: ReportGroup[]; empty: string }) {
  return (
    <Card className="min-w-0">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">{empty}</p>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Nhóm</TH>
                <TH className="text-right">Lần chạy</TH>
                <TH className="text-right">Đạt</TH>
                <TH className="text-right">Không đạt, lỗi</TH>
                <TH className="hidden text-right sm:table-cell">Bị chặn</TH>
                <TH className="text-right">Tỷ lệ đạt</TH>
              </TR>
            </THead>
            <TBody>
              {rows.map((g) => (
                <TR key={g.key ?? g.label}>
                  <TD className="font-medium">{g.label}</TD>
                  <TD className="text-right tabular-nums">{g.runs}</TD>
                  <TD className="text-right tabular-nums">{g.items.passed}</TD>
                  <TD className="text-right tabular-nums">{g.items.failed + g.items.error}</TD>
                  <TD className="hidden text-right tabular-nums sm:table-cell">{g.items.blocked}</TD>
                  <TD className="text-right tabular-nums">{formatPassRate(g.pass_rate)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function DailyChart({ data }: { data: ProjectReport["daily"] }) {
  const rows = data.map((d) => ({
    label: new Date(`${d.date}T00:00:00`).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" }),
    passed: d.items.passed,
    failed: d.items.failed + d.items.error,
    other: d.items.blocked + d.items.skipped + d.items.cancelled,
  }));
  return (
    <div className="h-64 w-full" role="img" aria-label="Biểu đồ kết quả test case theo ngày">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border)" />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
          <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="passed" name="Đạt" stackId="a" fill="var(--color-status-passed)" />
          <Bar dataKey="failed" name="Không đạt, lỗi" stackId="a" fill="var(--color-status-failed)" />
          <Bar dataKey="other" name="Bị chặn, bỏ qua, hủy" stackId="a" fill="var(--color-status-blocked)" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ReportsPage() {
  const { query: pq, projects, selected, select } = useProjectSelection();
  const [params, setParams] = useSearchParams();
  const filters = {
    environment_id: params.get("environment") ?? "",
    suite_id: params.get("suite") ?? "",
    date_from: params.get("from") ?? "",
    date_to: params.get("to") ?? "",
  };
  const setParam = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
  };
  const envs = useQuery({
    queryKey: ["environments", selected?.id],
    enabled: !!selected,
    queryFn: () => api<Environment[]>(`/api/projects/${selected?.id}/environments`),
  });
  const suites = useQuery({
    queryKey: ["suites", selected?.id],
    enabled: !!selected,
    queryFn: () => api<Suite[]>(`/api/projects/${selected?.id}/suites`),
  });
  const qs = reportQuery(filters);
  const report = useQuery({
    queryKey: ["report", selected?.id, qs],
    enabled: !!selected,
    placeholderData: keepPreviousData,
    queryFn: () => api<ProjectReport>(`/api/projects/${selected?.id}/reports/summary${qs ? `?${qs}` : ""}`),
  });
  const r = report.data;
  const exportUrl = (format: string) =>
    `/api/projects/${selected?.id}/reports/summary/export?${reportQuery({ ...filters, format })}`;

  return (
    <>
      <PageHeader
        title="Báo cáo"
        description="Tổng hợp kết quả kiểm thử theo dự án, môi trường, suite và khoảng ngày. Số liệu lấy trực tiếp từ kết quả đã chạy."
        actions={
          selected &&
          r && (
            <>
              <Button variant="outline" asChild>
                <a href={exportUrl("html")} target="_blank" rel="noopener">
                  <FileText /> HTML
                </a>
              </Button>
              <Button variant="outline" asChild>
                <a href={exportUrl("xlsx")}>
                  <Download /> Excel
                </a>
              </Button>
              <Button variant="outline" asChild>
                <a href={exportUrl("csv")}>
                  <Download /> CSV
                </a>
              </Button>
            </>
          )
        }
      />
      {pq.isPending && <LoadingState />}
      {pq.isError && <ErrorState message={pq.error.message} onRetry={() => pq.refetch()} />}
      {pq.data && projects.length === 0 && <EmptyState title="Chưa có dự án" />}
      {selected && (
        <div className="space-y-4">
          <Card>
            <CardContent className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 sm:p-5 lg:grid-cols-5">
              <ProjectPicker id="report-project" projects={projects} value={selected.id} onChange={select} />
              <div className="grid min-w-0 gap-1.5">
                <Label htmlFor="report-env">Môi trường</Label>
                <NativeSelect id="report-env" value={filters.environment_id} onChange={(e) => setParam("environment", e.target.value)}>
                  <option value="">Tất cả</option>
                  {envs.data?.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.name}
                    </option>
                  ))}
                </NativeSelect>
              </div>
              <div className="grid min-w-0 gap-1.5">
                <Label htmlFor="report-suite">Suite</Label>
                <NativeSelect id="report-suite" value={filters.suite_id} onChange={(e) => setParam("suite", e.target.value)}>
                  <option value="">Tất cả</option>
                  {suites.data?.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </NativeSelect>
              </div>
              <div className="grid min-w-0 gap-1.5">
                <Label htmlFor="report-from">Từ ngày</Label>
                <Input id="report-from" type="date" value={filters.date_from} onChange={(e) => setParam("from", e.target.value)} />
              </div>
              <div className="grid min-w-0 gap-1.5">
                <Label htmlFor="report-to">Đến ngày</Label>
                <Input id="report-to" type="date" value={filters.date_to} onChange={(e) => setParam("to", e.target.value)} />
              </div>
            </CardContent>
          </Card>
          {report.isPending && <LoadingState />}
          {report.isError && <ErrorState message={report.error.message} onRetry={() => report.refetch()} />}
          {r && (
            <>
              <p className="text-sm text-muted-foreground">
                Từ {new Date(`${r.filters.date_from}T00:00:00`).toLocaleDateString("vi-VN")} đến{" "}
                {new Date(`${r.filters.date_to}T00:00:00`).toLocaleDateString("vi-VN")} · lần chạy đã kết thúc · múi giờ {r.filters.timezone}
              </p>
              {r.runs === 0 ? (
                <EmptyState
                  icon={<BarChart3 className="size-6" />}
                  title="Chưa có lần chạy nào trong khoảng này"
                  description="Đổi bộ lọc hoặc chạy test để có số liệu báo cáo."
                />
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                    <Stat label="Lần chạy" value={r.runs} />
                    <Stat
                      label="Kết quả test case"
                      value={r.items.passed + r.items.failed + r.items.error + r.items.blocked + r.items.skipped + r.items.cancelled}
                    />
                    <Stat label="Tỷ lệ đạt" value={formatPassRate(r.pass_rate)} note="Đạt / (đạt + không đạt + lỗi + bị chặn)" />
                    <Stat label="Không đạt, lỗi, bị chặn" value={r.items.failed + r.items.error + r.items.blocked} />
                  </div>
                  <Card className="min-w-0">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Theo ngày</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <DailyChart data={r.daily} />
                    </CardContent>
                  </Card>
                  <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                    <GroupTable title="Theo môi trường" rows={r.by_environment} empty="Không có dữ liệu." />
                    <GroupTable title="Theo suite" rows={r.by_suite} empty="Không có dữ liệu." />
                  </div>
                  <Card className="min-w-0">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Theo test case</CardTitle>
                      <p className="text-sm text-muted-foreground">
                        Test lỗi nhiều nhất lên đầu.
                        {r.test_cases.length > CASE_LIMIT && ` Hiển thị ${CASE_LIMIT}/${r.test_cases.length}; xuất Excel để xem đủ.`}
                      </p>
                    </CardHeader>
                    <CardContent>
                      <Table>
                        <THead>
                          <TR>
                            <TH>Test case</TH>
                            <TH className="text-right">Số lần</TH>
                            <TH className="hidden text-right sm:table-cell">Đạt</TH>
                            <TH className="hidden text-right sm:table-cell">Không đạt, lỗi</TH>
                            <TH className="text-right">Tỷ lệ đạt</TH>
                            <TH>Gần nhất</TH>
                          </TR>
                        </THead>
                        <TBody>
                          {r.test_cases.slice(0, CASE_LIMIT).map((c) => (
                            <TR key={c.code}>
                              <TD className="min-w-0">
                                <p className="font-medium break-words">{c.title}</p>
                                <p className="text-xs text-muted-foreground">
                                  {c.code}
                                  {c.last_error && <span className="block break-words text-status-failed">{c.last_error}</span>}
                                </p>
                              </TD>
                              <TD className="text-right tabular-nums">{c.executions}</TD>
                              <TD className="hidden text-right tabular-nums sm:table-cell">{c.items.passed}</TD>
                              <TD className="hidden text-right tabular-nums sm:table-cell">{c.items.failed + c.items.error}</TD>
                              <TD className="text-right tabular-nums">{formatPassRate(c.pass_rate)}</TD>
                              <TD>
                                <Link to={`/test-runs/${c.last_run_id}`} className="inline-flex flex-col gap-1 hover:underline">
                                  <StatusBadge status={c.last_status} />
                                  <span className="text-xs text-muted-foreground">{formatDateTime(c.last_finished_at)}</span>
                                </Link>
                              </TD>
                            </TR>
                          ))}
                        </TBody>
                      </Table>
                    </CardContent>
                  </Card>
                </>
              )}
            </>
          )}
        </div>
      )}
    </>
  );
}
