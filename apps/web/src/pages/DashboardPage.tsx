import { useQuery } from "@tanstack/react-query";
import { Activity, FolderKanban, ListChecks, PlayCircle, Server, Users } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { STATUS_META, type RunStatus } from "@/lib/status";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useMe } from "@/hooks/auth";
import { api, type Dashboard } from "@/lib/api";
import { auditLabel, auditSummary } from "@/lib/audit-labels";
import { formatDateTime } from "@/lib/utils";

function StatCard({ label, value, icon, note }: { label: string; value: ReactNode; icon: ReactNode; note?: string | null }) {
  return (
    <Card>
      <CardContent className="flex items-start justify-between gap-3 p-5">
        <div className="min-w-0 space-y-1">
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="text-2xl font-semibold tabular-nums">{value}</p>
          {note && <p className="text-xs text-muted-foreground">{note}</p>}
        </div>
        <div className="rounded-lg bg-accent p-2 text-accent-foreground">{icon}</div>
      </CardContent>
    </Card>
  );
}

const RESULT_STATUSES: RunStatus[] = ["passed", "failed", "error", "blocked", "skipped", "cancelled"];

function RunHistoryChart({ data }: { data: Dashboard["daily"] }) {
  const rows = data.map((d) => ({ ...d, label: new Date(`${d.date}T00:00:00`).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" }) }));
  return (
    <div className="h-64 w-full" role="img" aria-label="Biểu đồ số test case đạt và lỗi theo ngày">
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

export function DashboardPage() {
  const { data: me } = useMe();
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dashboard>("/api/dashboard") });

  return (
    <>
      <PageHeader title="Số liệu tổng quan" description="Số liệu dự án, kết quả theo ngày và hoạt động kiểm thử." />
      {q.isPending && <LoadingState rows={4} />}
      {q.isError && <ErrorState message={q.error.message} onRetry={() => q.refetch()} />}
      {q.data && (
        <div className="space-y-6">
          {q.data.projects === 0 ? (
            <EmptyState
              icon={<FolderKanban className="size-6" />}
              title="Chưa có dự án nào"
              description={
                me?.is_system_admin
                  ? "Tạo dự án đầu tiên để khai báo môi trường và bắt đầu quản lý kiểm thử."
                  : "Bạn chưa được thêm vào dự án nào. Hãy liên hệ quản trị hệ thống."
              }
              action={
                me?.is_system_admin && (
                  <Button asChild>
                    <Link to="/projects?new=1">Tạo dự án</Link>
                  </Button>
                )
              }
            />
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <StatCard label="Dự án" value={q.data.projects} icon={<FolderKanban className="size-5" />} />
            <StatCard label="Môi trường" value={q.data.environments} icon={<Server className="size-5" />} />
            <StatCard label="Thành viên" value={q.data.members} icon={<Users className="size-5" />} />
            <StatCard label="Test case" value={q.data.test_cases} icon={<ListChecks className="size-5" />} />
            <StatCard
              label="Lần chạy"
              value={q.data.runs_total}
              note={q.data.active_runs > 0 ? `${q.data.active_runs} đang thực thi` : null}
              icon={<PlayCircle className="size-5" />}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <CardHeader>
                <CardTitle>Kết quả {q.data.period_days} ngày gần nhất</CardTitle>
                <CardDescription>
                  {q.data.pass_rate === null
                    ? "Chưa có kết quả chạy test trong kỳ."
                    : `Tỷ lệ đạt ${q.data.pass_rate.toLocaleString("vi-VN")}% trên các test case đã thực thi (không tính bỏ qua và đã hủy).`}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap gap-2" aria-label="Tổng theo trạng thái">
                  {RESULT_STATUSES.map((s) => (
                    <span key={s} className={`rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_META[s].className}`}>
                      {STATUS_META[s].label}: {q.data.item_totals[s] ?? 0}
                    </span>
                  ))}
                </div>
                {q.data.pass_rate === null ? (
                  <EmptyState
                    icon={<Activity className="size-6" />}
                    title="Chưa có lần chạy test nào trong kỳ"
                    description="Biểu đồ hiển thị số liệu thật sau khi có lần chạy kết thúc."
                  />
                ) : (
                  <RunHistoryChart data={q.data.daily} />
                )}
              </CardContent>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Hoạt động gần đây</CardTitle>
                <CardDescription>Thao tác quan trọng trong các dự án của bạn.</CardDescription>
              </CardHeader>
              <CardContent>
                {q.data.recent_activity.length === 0 ? (
                  <p className="py-6 text-center text-sm text-muted-foreground">Chưa có hoạt động.</p>
                ) : (
                  <ol className="space-y-3">
                    {q.data.recent_activity.map((a) => (
                      <li key={a.id} className="flex gap-3 text-sm">
                        <span className="mt-1.5 size-2 shrink-0 rounded-full bg-primary/60" aria-hidden />
                        <div className="min-w-0">
                          <p className="font-medium">
                            {auditLabel(a.action)}
                            {auditSummary(a.details) && (
                              <span className="font-normal text-muted-foreground"> · {auditSummary(a.details)}</span>
                            )}
                          </p>
                          <p className="truncate text-xs text-muted-foreground">
                            {a.actor_email ?? "Hệ thống"} · {formatDateTime(a.created_at)}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Lần chạy gần đây</CardTitle>
              </CardHeader>
              <CardContent>
                {q.data.recent_runs.length === 0 ? (
                  <p className="py-6 text-center text-sm text-muted-foreground">Chưa có lần chạy.</p>
                ) : (
                  <ul className="divide-y">
                    {q.data.recent_runs.map((r) => (
                      <li key={r.id} className="flex items-center gap-3 py-2 text-sm">
                        <div className="min-w-0 flex-1">
                          <Link to={`/test-runs/${r.id}`} className="block truncate font-medium hover:underline">
                            {r.title}
                          </Link>
                          <p className="truncate text-xs text-muted-foreground">
                            {r.project_key} · {r.environment_name} · {formatDateTime(r.created_at)}
                          </p>
                        </div>
                        <span className="text-xs tabular-nums text-muted-foreground">
                          {r.passed}/{r.total}
                        </span>
                        <StatusBadge status={r.status} />
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Cần chú ý</CardTitle>
                <CardDescription>Test case có kết quả gần nhất là lỗi hoặc bị chặn.</CardDescription>
              </CardHeader>
              <CardContent>
                {q.data.attention.length === 0 ? (
                  <p className="py-6 text-center text-sm text-muted-foreground">Không có test case nào đang lỗi.</p>
                ) : (
                  <ul className="divide-y">
                    {q.data.attention.map((a) => (
                      <li key={a.item_id} className="grid gap-1 py-2 text-sm">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs">{a.code}</span>
                          <Link to={`/test-runs/${a.run_id}`} className="min-w-0 flex-1 truncate font-medium hover:underline">
                            {a.title}
                          </Link>
                          <StatusBadge status={a.status} />
                        </div>
                        {a.error && <p className="line-clamp-2 text-xs text-muted-foreground">{a.error}</p>}
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
