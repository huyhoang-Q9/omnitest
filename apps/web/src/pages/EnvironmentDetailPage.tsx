import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingState } from "@/components/states";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EnvironmentFormDialog, EnvKindBadge } from "@/features/environments";
import { VariablesPanel } from "@/features/variables";
import { api, ApiError, can, type Environment, type Project } from "@/lib/api";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

export function EnvironmentDetailPage() {
  const { environmentId = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const env = useQuery({
    queryKey: ["environment", environmentId],
    queryFn: () => api<Environment>(`/api/environments/${environmentId}`),
  });
  const project = useQuery({
    queryKey: ["project", env.data?.project_id],
    queryFn: () => api<Project>(`/api/projects/${env.data?.project_id}`),
    enabled: !!env.data,
  });
  const del = useMutation({
    mutationFn: () => api<void>(`/api/environments/${environmentId}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Đã xóa môi trường");
      void qc.invalidateQueries({ queryKey: ["environments"] });
      void qc.invalidateQueries({ queryKey: ["project", env.data?.project_id] });
      navigate(`/projects/${env.data?.project_id}`);
    },
    onError: (e) => toast.error(e.message),
  });

  if (env.isPending || (env.data && project.isPending)) return <LoadingState rows={5} />;
  if (env.isError)
    return (
      <ErrorState
        message={env.error instanceof ApiError && env.error.status === 404 ? "Môi trường không tồn tại hoặc bạn không có quyền truy cập." : env.error.message}
        onRetry={() => env.refetch()}
      />
    );
  if (project.isError) return <ErrorState message={project.error.message} onRetry={() => project.refetch()} />;

  const e = env.data;
  const p = project.data!;
  const role = p.my_role;
  const writable = !p.is_archived;

  return (
    <>
      <PageHeader
        breadcrumb={
          <span>
            <Link to="/projects" className="hover:underline">
              Dự án
            </Link>{" "}
            /{" "}
            <Link to={`/projects/${p.id}`} className="hover:underline">
              {p.name}
            </Link>
          </span>
        }
        title={
          <span className="flex items-center gap-2">
            {e.name} <EnvKindBadge kind={e.kind} />
          </span>
        }
        actions={
          writable && (
            <>
              {can(role, "manager") && (
                <Button variant="outline" onClick={() => setEditing(true)}>
                  <Pencil /> Sửa
                </Button>
              )}
              {can(role, "admin") && (
                <Button variant="outline" onClick={() => setDeleting(true)}>
                  <Trash2 className="text-status-failed" /> Xóa
                </Button>
              )}
            </>
          )
        }
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Thông tin</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-4">
              <Field label="Base URL">
                <span className="break-all font-mono text-xs">{e.base_url}</span>
              </Field>
              <Field label="Host đích được phép">
                {e.allowed_hosts.length ? (
                  <span className="flex flex-wrap gap-1">
                    {e.allowed_hosts.map((h) => (
                      <Badge key={h} variant="outline" className="font-mono">
                        {h}
                      </Badge>
                    ))}
                  </span>
                ) : (
                  <span className="text-muted-foreground">Chỉ host của Base URL</span>
                )}
              </Field>
              <Field label="Bảo vệ">
                <span className="flex flex-wrap gap-1">
                  <Badge variant={e.requires_run_confirmation ? "warning" : "muted"}>
                    {e.requires_run_confirmation ? "Cần xác nhận trước khi chạy" : "Không cần xác nhận"}
                  </Badge>
                  <Badge variant={e.allow_private_network ? "warning" : "muted"}>
                    {e.allow_private_network ? "Cho phép mạng nội bộ" : "Chặn mạng nội bộ"}
                  </Badge>
                </span>
              </Field>
              {e.description && <Field label="Mô tả">{e.description}</Field>}
            </dl>
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Biến môi trường</CardTitle>
          </CardHeader>
          <CardContent>
            <VariablesPanel environmentId={e.id} canEdit={can(role, "manager") && writable} />
          </CardContent>
        </Card>
      </div>
      <EnvironmentFormDialog open={editing} onOpenChange={setEditing} projectId={p.id} environment={e} role={role} />
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Xóa môi trường ${e.name}?`}
        description="Toàn bộ biến của môi trường này cũng bị xóa. Thao tác không hoàn tác được."
        confirmLabel="Xóa môi trường"
        loading={del.isPending}
        onConfirm={() => del.mutate()}
      />
    </>
  );
}
