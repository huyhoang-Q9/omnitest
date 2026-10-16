import { useQuery } from "@tanstack/react-query";
import { Activity, FolderKanban, ListChecks, PlayCircle, Server, Users } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
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

const RESULT_STATUSES: RunStatus[] = ["passed", "failed", "skipped", "blocked"];

export function DashboardPage() {
  const { data: me } = useMe();
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dashboard>("/api/dashboard") });

  return (
    <>
      <PageHeader title="Dashboard" description="Tổng quan dự án và hoạt động kiểm thử." />
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
            <StatCard
              label="Test case"
              value={q.data.test_cases.value ?? "Chưa có"}
              note={q.data.test_cases.note}
              icon={<ListChecks className="size-5" />}
            />
            <StatCard
              label="Lần chạy"
              value={q.data.test_runs.value ?? "Chưa có"}
              note={q.data.test_runs.note}
              icon={<PlayCircle className="size-5" />}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <CardHeader>
                <CardTitle>Kết quả và lịch sử chạy test</CardTitle>
                <CardDescription>Tỷ lệ thành công và biểu đồ theo thời gian.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap gap-2" aria-label="Chú giải trạng thái">
                  {RESULT_STATUSES.map((s) => (
                    <span key={s} className={`rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_META[s].className}`}>
                      {STATUS_META[s].label}: chưa có
                    </span>
                  ))}
                </div>
                <EmptyState
                  icon={<Activity className="size-6" />}
                  title="Chưa có lần chạy test nào"
                  description="Biểu đồ hiển thị số liệu thật sau khi chức năng chạy test có ở Giai đoạn 3."
                />
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
        </div>
      )}
    </>
  );
}
