import { useQuery } from "@tanstack/react-query";
import { Radio } from "lucide-react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { CancelRunButton, RunProgress } from "@/features/runs";
import { api, type Run } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export function LivePage() {
  const q = useQuery({
    queryKey: ["active-runs"],
    queryFn: () => api<Run[]>("/api/runs/active"),
    refetchInterval: 2000,
  });
  return (
    <>
      <PageHeader title="Đang thực thi" description="Các lần chạy đang chờ hoặc đang chạy trong những dự án bạn tham gia. Tự cập nhật mỗi 2 giây." />
      {q.isPending && <LoadingState />}
      {q.isError && <ErrorState message={q.error.message} onRetry={() => q.refetch()} />}
      {q.data &&
        (q.data.length === 0 ? (
          <EmptyState icon={<Radio className="size-6" />} title="Không có lần chạy nào đang thực thi" description="Lần chạy mới sẽ xuất hiện ở đây ngay khi được tạo." />
        ) : (
          <div className="grid gap-4 lg:grid-cols-2" aria-live="polite">
            {q.data.map((r) => (
              <Card key={r.id}>
                <CardContent className="grid gap-3 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <Link to={`/test-runs/${r.id}`} className="font-medium hover:underline">
                        {r.title}
                      </Link>
                      <p className="text-xs text-muted-foreground">
                        {r.project_key} · {r.environment_name} · {r.triggered_by_email ?? "Hệ thống"} · {formatDateTime(r.created_at)}
                      </p>
                    </div>
                    <StatusBadge status={r.status} />
                  </div>
                  <RunProgress run={r} />
                  <div className="flex justify-end">
                    <CancelRunButton run={r} />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ))}
    </>
  );
}
