import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Download, FileArchive, ImageIcon } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CancelRunButton, RunProgress } from "@/features/runs";
import { api, type Artifact, type RunDetail, type RunItem, type RunItemDetail, type StepResult } from "@/lib/api";
import { isActive } from "@/lib/status";
import { ERROR_TYPE_LABEL, formatBytes, formatDuration, TEST_TYPE_LABEL } from "@/lib/test-labels";
import { cn, formatDateTime } from "@/lib/utils";

function ArtifactList({ artifacts }: { artifacts: Artifact[] }) {
  if (artifacts.length === 0) return null;
  const shots = artifacts.filter((a) => a.content_type === "image/png");
  const files = artifacts.filter((a) => a.content_type !== "image/png");
  return (
    <div className="grid gap-3">
      {shots.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {shots.map((a) => (
            <figure key={a.id} className="overflow-hidden rounded-md border">
              <a href={`/api/artifacts/${a.id}`} target="_blank" rel="noreferrer">
                <img src={`/api/artifacts/${a.id}`} alt={`Ảnh chụp ${a.filename}`} loading="lazy" className="w-full bg-muted" />
              </a>
              <figcaption className="flex items-center gap-2 px-2 py-1 text-xs text-muted-foreground">
                <ImageIcon className="size-3" /> {a.filename} · {formatBytes(a.size)}
              </figcaption>
            </figure>
          ))}
        </div>
      )}
      {files.map((a) => (
        <a key={a.id} href={`/api/artifacts/${a.id}`} className="flex w-fit items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted">
          {a.kind === "trace" ? <FileArchive className="size-4" /> : <Download className="size-4" />}
          {a.kind === "trace" ? "Tải trace Playwright" : a.filename} · {formatBytes(a.size)}
        </a>
      ))}
      {files.some((a) => a.kind === "trace") && (
        <p className="text-xs text-muted-foreground">Mở trace bằng lệnh: npx playwright show-trace &lt;file.zip&gt;</p>
      )}
    </div>
  );
}

function StepRow({ step, artifacts }: { step: StepResult; artifacts: Artifact[] }) {
  const [open, setOpen] = useState(step.status !== "passed");
  const details = step.details as { request?: unknown; response?: unknown; assertions?: unknown };
  return (
    <li className="rounded-md border">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open ? <ChevronDown className="size-4 shrink-0" /> : <ChevronRight className="size-4 shrink-0" />}
        <span className="w-6 shrink-0 tabular-nums text-muted-foreground">{step.index + 1}</span>
        <span className="min-w-0 flex-1 truncate">{step.name}</span>
        <span className="hidden text-xs text-muted-foreground sm:inline">{formatDuration(step.duration_ms)}</span>
        <StatusBadge status={step.status} />
      </button>
      {open && (
        <div className="grid gap-3 border-t px-3 py-3 text-sm">
          {step.error && (
            <p role="alert" className="whitespace-pre-wrap rounded-md bg-status-failed/8 p-2 text-status-failed">
              {step.error}
            </p>
          )}
          {step.log.length > 0 && (
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-2 font-mono text-xs">{step.log.join("\n")}</pre>
          )}
          {(details.request !== undefined || details.response !== undefined) && (
            <details className="text-xs">
              <summary className="cursor-pointer font-medium">Request và response (đã che secret)</summary>
              <pre className="mt-2 max-h-96 overflow-auto rounded-md bg-muted p-2 font-mono">
                {JSON.stringify({ request: details.request, response: details.response }, null, 2)}
              </pre>
            </details>
          )}
          <ArtifactList artifacts={artifacts} />
        </div>
      )}
    </li>
  );
}

function ItemDetail({ item, live }: { item: RunItem; live: boolean }) {
  const q = useQuery({
    queryKey: ["run-item", item.id, item.status],
    queryFn: () => api<RunItemDetail>(`/api/run-items/${item.id}`),
    refetchInterval: live && item.status === "running" ? 2000 : false,
  });
  if (q.isPending) return <LoadingState rows={2} />;
  if (q.isError) return <ErrorState message={q.error.message} onRetry={() => q.refetch()} />;
  const d = q.data;
  const attempts = [...new Set(d.steps.map((s) => s.attempt))];
  const byStep = (id: string) => d.artifacts.filter((a) => a.step_result_id === id);
  const loose = d.artifacts.filter((a) => !a.step_result_id);
  return (
    <div className="grid gap-4">
      {d.error && (
        <div role="alert" className="rounded-md border border-status-failed/30 bg-status-failed/5 p-3 text-sm">
          {d.error_type && <p className="font-medium">{ERROR_TYPE_LABEL[d.error_type] ?? d.error_type}</p>}
          <p className="whitespace-pre-wrap">{d.error}</p>
        </div>
      )}
      {d.steps.length === 0 && !isActive(d.status) && <p className="text-sm text-muted-foreground">Không có bước nào được thực thi.</p>}
      {attempts.map((a) => (
        <div key={a} className="grid gap-2">
          {attempts.length > 1 && <p className="text-sm font-medium">Lần thử {a}</p>}
          <ol className="grid gap-2">
            {d.steps
              .filter((s) => s.attempt === a)
              .map((s) => (
                <StepRow key={s.id} step={s} artifacts={byStep(s.id)} />
              ))}
          </ol>
        </div>
      ))}
      <ArtifactList artifacts={loose} />
    </div>
  );
}

export function RunDetailPage() {
  const { runId = "" } = useParams();
  const [openItem, setOpenItem] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api<RunDetail>(`/api/runs/${runId}`),
    refetchInterval: (query) => (query.state.data && isActive(query.state.data.status) ? 2000 : false),
  });
  if (q.isPending) return <LoadingState rows={6} />;
  if (q.isError) return <ErrorState message={q.error.message} onRetry={() => q.refetch()} />;
  const run = q.data;
  const live = isActive(run.status);
  const selected = openItem ?? run.items.find((i) => i.status !== "passed" && !isActive(i.status))?.id ?? null;

  return (
    <>
      <PageHeader
        breadcrumb={
          <Link to={`/test-runs?project=${run.project_id}`} className="hover:underline">
            Lần chạy {run.project_key ? `· ${run.project_key}` : ""}
          </Link>
        }
        title={run.title}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={run.status} /> Môi trường {run.environment_name} · {run.triggered_by_email ?? "Hệ thống"} ·{" "}
            {formatDateTime(run.created_at)}
          </span>
        }
        actions={<CancelRunButton run={run} size="default" />}
      />
      <div className="grid gap-6">
        <Card>
          <CardContent className="grid gap-4 p-4 sm:grid-cols-4 sm:p-5">
            <div className="sm:col-span-2">
              <RunProgress run={run} />
            </div>
            <div className="text-sm">
              <p className="text-muted-foreground">Bắt đầu</p>
              <p>{formatDateTime(run.started_at)}</p>
            </div>
            <div className="text-sm">
              <p className="text-muted-foreground">Thời lượng</p>
              <p>{live ? "Đang chạy" : formatDuration(run.duration_ms)}</p>
            </div>
            {run.error && (
              <p role="alert" className="text-sm text-status-failed sm:col-span-4">
                {run.error}
              </p>
            )}
            {live && (
              <p className="text-xs text-muted-foreground sm:col-span-4" aria-live="polite">
                Tự cập nhật mỗi 2 giây{run.status === "queued" ? ". Đang chờ worker nhận việc." : "."}
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Test case ({run.items.length})</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2">
            {run.items.map((item) => {
              const isOpen = selected === item.id;
              return (
                <div key={item.id} className={cn("rounded-lg border", isOpen && "border-primary/40")}>
                  <button
                    type="button"
                    className="flex w-full flex-wrap items-center gap-3 px-3 py-3 text-left"
                    aria-expanded={isOpen}
                    onClick={() => setOpenItem(isOpen ? "" : item.id)}
                  >
                    {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                    <span className="font-mono text-xs">{item.code}</span>
                    <span className="min-w-0 flex-1 truncate font-medium">{item.title}</span>
                    <Badge variant="outline">{TEST_TYPE_LABEL[item.test_type]}</Badge>
                    {item.attempts > 1 && <Badge variant="muted">{item.attempts} lần thử</Badge>}
                    <span className="text-xs text-muted-foreground">{formatDuration(item.duration_ms)}</span>
                    <StatusBadge status={item.status} />
                  </button>
                  {isOpen && (
                    <div className="border-t p-3">
                      <ItemDetail item={item} live={live} />
                    </div>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
