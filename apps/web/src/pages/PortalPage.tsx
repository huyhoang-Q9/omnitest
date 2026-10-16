import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BarChart3, FileCode2, Globe, Layers, PlayCircle, Radio, Zap } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useMe } from "@/hooks/auth";
import { api, ENV_KIND_LABEL, type Dashboard, type Environment, type Page, type Project } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

function ActionTile({ to, icon, title, description }: { to: string; icon: ReactNode; title: string; description: string }) {
  return (
    <Link
      to={to}
      className="group flex gap-4 rounded-xl border bg-card p-5 shadow-xs transition hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <span className="grid size-11 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1 font-semibold">
          {title}
          <ArrowRight className="size-4 opacity-0 transition group-hover:translate-x-0.5 group-hover:opacity-100" aria-hidden />
        </span>
        <span className="mt-0.5 block text-sm text-muted-foreground">{description}</span>
      </span>
    </Link>
  );
}

function Metric({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div className="rounded-lg bg-white/10 px-4 py-3">
      <p className="text-xs text-white/75">{label}</p>
      <p className={`text-2xl font-semibold tabular-nums ${tone ?? ""}`}>{value}</p>
    </div>
  );
}

/** Hệ thống (môi trường) của một dự án, mỗi hệ thống có nút kiểm thử ngay. */
function ProjectSystems({ project }: { project: Project }) {
  const envs = useQuery({
    queryKey: ["environments", project.id],
    queryFn: () => api<Environment[]>(`/api/projects/${project.id}/environments`),
  });
  if (envs.isPending)
    return (
      <li className="py-2.5">
        <LoadingState rows={1} />
      </li>
    );
  if (envs.isError) return <li className="py-2.5 text-sm text-status-failed">{envs.error.message}</li>;
  if (envs.data.length === 0)
    return (
      <li className="py-2.5 text-sm text-muted-foreground">
        {project.key}: chưa có hệ thống.{" "}
        <Link to={`/test?project=${project.id}`} className="text-primary hover:underline">
          Thêm hệ thống
        </Link>
      </li>
    );
  return (
    <>
      {envs.data.map((e) => (
        <li key={e.id} className="flex items-center gap-3 py-2.5">
          <Globe className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">
              {e.name} <span className="font-normal text-muted-foreground">· {project.key} · {ENV_KIND_LABEL[e.kind]}</span>
            </p>
            <p className="truncate text-xs text-muted-foreground">{e.base_url}</p>
          </div>
          <Button asChild size="sm" variant="outline">
            <Link to={`/test?project=${project.id}&env=${e.id}`} aria-label={`Kiểm thử ${e.name} của ${project.key}`}>
              <PlayCircle /> Kiểm thử
            </Link>
          </Button>
        </li>
      ))}
    </>
  );
}

/** Trang chủ dạng cổng kiểm thử: hành động chính lên đầu, số liệu thật từ API ngay bên dưới. */
export function PortalPage() {
  const { data: me } = useMe();
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dashboard>("/api/dashboard") });
  const projects = useQuery({
    queryKey: ["projects", { all: true }],
    queryFn: () => api<Page<Project>>("/api/projects?page_size=100"),
  });
  // Dự án vừa có lần chạy lên trước, để hệ thống người dùng đang làm việc nằm ở đầu danh sách.
  const recentKeys = dash.data?.recent_runs.map((r) => r.project_key) ?? [];
  const rank = (p: Project) => {
    const i = recentKeys.indexOf(p.key);
    return i === -1 ? recentKeys.length : i;
  };
  const shownProjects = [...(projects.data?.items ?? [])].sort((a, b) => rank(a) - rank(b)).slice(0, 4);

  return (
    <div className="space-y-8">
      <section className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-primary to-sidebar p-6 text-white shadow-md sm:p-8">
        <div className="relative grid gap-6 lg:grid-cols-[1.4fr_1fr] lg:items-center">
          <div className="space-y-4">
            <p className="text-sm text-white/80">Xin chào{me ? `, ${me.full_name}` : ""}</p>
            <h1 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">Cổng kiểm thử tự động OmniTest</h1>
            <p className="max-w-xl text-white/85">
              Chọn hệ thống, chọn nội dung kiểm thử và bấm chạy. Kết quả từng bước, ảnh chụp màn hình và báo cáo có ngay sau đó.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button asChild size="lg" className="bg-white text-primary hover:bg-white/90">
                <Link to="/test">
                  <Zap /> Kiểm thử ngay
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline" className="border-white/40 bg-transparent text-white hover:bg-white/10">
                <Link to="/test-runs">Xem kết quả</Link>
              </Button>
            </div>
          </div>
          {dash.data && (
            <div className="grid grid-cols-2 gap-3">
              <Metric label={`Tỷ lệ đạt ${dash.data.period_days} ngày`} value={dash.data.pass_rate === null ? "Chưa có" : `${dash.data.pass_rate.toLocaleString("vi-VN")}%`} />
              <Metric label="Đang thực thi" value={dash.data.active_runs} />
              <Metric label="Test case" value={dash.data.test_cases} />
              <Metric label="Lần chạy" value={dash.data.runs_total} />
            </div>
          )}
        </div>
      </section>

      <section aria-labelledby="portal-actions" className="space-y-3">
        <h2 id="portal-actions" className="text-lg font-semibold">
          Bạn muốn làm gì?
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <ActionTile to="/test?mode=quick" icon={<Zap className="size-5" />} title="Kiểm tra nhanh" description="Hệ thống có phản hồi, trang web có mở được không." />
          <ActionTile to="/test?mode=suite" icon={<Layers className="size-5" />} title="Chạy bộ test" description="Chạy một bộ test đã soạn cho dự án." />
          <ActionTile to="/test-cases/new" icon={<FileCode2 className="size-5" />} title="Soạn test case" description="API, Web, script code hoặc ứng dụng." />
          <ActionTile to="/reports" icon={<BarChart3 className="size-5" />} title="Báo cáo" description="Xuất HTML, CSV, Excel theo lần chạy hoặc dự án." />
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Hệ thống của bạn</CardTitle>
            <CardDescription>Môi trường trong các dự án bạn tham gia. Bấm "Kiểm thử" để bắt đầu.</CardDescription>
          </CardHeader>
          <CardContent>
            {projects.isPending && <LoadingState rows={2} />}
            {projects.isError && <ErrorState message={projects.error.message} onRetry={() => projects.refetch()} />}
            {projects.data?.items.length === 0 && (
              <p className="py-4 text-sm text-muted-foreground">
                Bạn chưa thuộc dự án nào.{" "}
                {me?.is_system_admin ? (
                  <Link to="/projects?new=1" className="text-primary hover:underline">
                    Tạo dự án
                  </Link>
                ) : (
                  "Hãy nhờ quản trị hệ thống thêm bạn vào dự án."
                )}
              </p>
            )}
            <ul className="divide-y">
              {shownProjects.map((p) => (
                <ProjectSystems key={p.id} project={p} />
              ))}
            </ul>
            {(projects.data?.items.length ?? 0) > shownProjects.length && (
              <Link to="/environments" className="mt-2 inline-block text-sm text-primary hover:underline">
                Xem tất cả môi trường
              </Link>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
            <div className="space-y-1">
              <CardTitle>Lần chạy gần đây</CardTitle>
              <CardDescription>Bấm vào để xem từng bước, ảnh và log.</CardDescription>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link to="/live">
                <Radio /> Trực tiếp
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {dash.isPending && <LoadingState rows={2} />}
            {dash.isError && <ErrorState message={dash.error.message} onRetry={() => dash.refetch()} />}
            {dash.data?.recent_runs.length === 0 && <p className="py-4 text-sm text-muted-foreground">Chưa có lần chạy nào.</p>}
            <ul className="divide-y">
              {dash.data?.recent_runs.map((r) => (
                <li key={r.id} className="flex items-center gap-3 py-2.5 text-sm">
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
            <Link to="/dashboard" className="mt-2 inline-block text-sm text-primary hover:underline">
              Xem số liệu tổng quan
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
