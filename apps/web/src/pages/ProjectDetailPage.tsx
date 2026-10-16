import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, Pencil, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";
import { FormField } from "@/components/form-field";
import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingState } from "@/components/states";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { ProjectAIToggle } from "@/features/ai";
import { ProjectScriptToggle } from "@/features/script";
import { AuditPanel } from "@/features/audit";
import { EnvironmentFormDialog, EnvironmentsTable } from "@/features/environments";
import { MembersPanel } from "@/features/members";
import { api, ApiError, can, ROLE_LABEL, type Project } from "@/lib/api";
import { cn } from "@/lib/utils";

type Tab = "environments" | "members" | "audit";

const editSchema = z.object({ name: z.string().trim().min(1, "Vui lòng nhập tên").max(200), description: z.string().max(5000) });

function EditProjectDialog({ project, open, onOpenChange }: { project: Project; open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const form = useForm<z.infer<typeof editSchema>>({ resolver: zodResolver(editSchema) });
  useEffect(() => {
    if (open) form.reset({ name: project.name, description: project.description });
  }, [open, project, form]);
  const m = useMutation({
    mutationFn: (v: z.infer<typeof editSchema>) => api<Project>(`/api/projects/${project.id}`, { method: "PATCH", json: v }),
    onSuccess: (p) => {
      qc.setQueryData(["project", p.id], p);
      void qc.invalidateQueries({ queryKey: ["projects"] });
      toast.success("Đã lưu dự án");
      onOpenChange(false);
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Sửa dự án {project.key}</DialogTitle>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={form.handleSubmit((v) => m.mutate(v))} noValidate>
          <FormField id="pe-name" label="Tên dự án" required error={form.formState.errors.name?.message}>
            <Input id="pe-name" {...form.register("name")} />
          </FormField>
          <FormField id="pe-desc" label="Mô tả">
            <Textarea id="pe-desc" {...form.register("description")} />
          </FormField>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Hủy
            </Button>
            <Button type="submit" loading={m.isPending}>
              Lưu
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) ?? "environments";
  const [editing, setEditing] = useState(false);
  const [envOpen, setEnvOpen] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);

  const q = useQuery({ queryKey: ["project", projectId], queryFn: () => api<Project>(`/api/projects/${projectId}`) });
  const archive = useMutation({
    mutationFn: (restore: boolean) =>
      api<Project>(`/api/projects/${projectId}/${restore ? "restore" : "archive"}`, { method: "POST" }),
    onSuccess: (p) => {
      qc.setQueryData(["project", p.id], p);
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success(p.is_archived ? "Đã lưu trữ dự án" : "Đã khôi phục dự án");
      setConfirmArchive(false);
    },
    onError: (e) => toast.error(e.message),
  });

  if (q.isPending) return <LoadingState rows={5} />;
  if (q.isError)
    return q.error instanceof ApiError && q.error.status === 404 ? (
      <ErrorState message="Dự án không tồn tại hoặc bạn không có quyền truy cập." />
    ) : (
      <ErrorState message={q.error.message} onRetry={() => q.refetch()} />
    );

  const p = q.data;
  const role = p.my_role;
  const tabs: { id: Tab; label: string; show: boolean }[] = [
    { id: "environments", label: `Môi trường (${p.environment_count})`, show: true },
    { id: "members", label: `Thành viên (${p.member_count})`, show: true },
    { id: "audit", label: "Nhật ký", show: can(role, "manager") },
  ];

  return (
    <>
      <PageHeader
        breadcrumb={
          <Link to="/projects" className="hover:underline">
            Dự án
          </Link>
        }
        title={
          <span className="flex flex-wrap items-center gap-2">
            {p.name}
            <Badge variant="outline">{p.key}</Badge>
            {p.is_archived && <Badge variant="muted">Đã lưu trữ</Badge>}
          </span>
        }
        description={p.description || "Chưa có mô tả."}
        actions={
          <>
            {can(role, "manager") && !p.is_archived && (
              <Button variant="outline" onClick={() => setEditing(true)}>
                <Pencil /> Sửa
              </Button>
            )}
            {can(role, "admin") &&
              (p.is_archived ? (
                <Button variant="outline" onClick={() => archive.mutate(true)} loading={archive.isPending}>
                  <ArchiveRestore /> Khôi phục
                </Button>
              ) : (
                <Button variant="outline" onClick={() => setConfirmArchive(true)}>
                  <Archive /> Lưu trữ
                </Button>
              ))}
          </>
        }
      />
      <p className="-mt-3 mb-5 text-sm text-muted-foreground">
        Vai trò của bạn: <span className="font-medium text-foreground">{role ? ROLE_LABEL[role] : "Không rõ"}</span>
      </p>
      <ProjectAIToggle project={p} canEdit={can(role, "admin")} />
      <ProjectScriptToggle project={p} canEdit={can(role, "admin")} />
      {p.is_archived && (
        <div role="status" className="mb-4 rounded-lg border border-status-blocked/30 bg-status-blocked/10 px-4 py-3 text-sm">
          Dự án đang lưu trữ nên chỉ xem được. Admin có thể khôi phục để chỉnh sửa tiếp.
        </div>
      )}

      <div role="tablist" aria-label="Nội dung dự án" className="mb-4 flex gap-1 overflow-x-auto border-b">
        {tabs
          .filter((t) => t.show)
          .map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setParams({ tab: t.id }, { replace: true })}
              className={cn(
                "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                tab === t.id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </button>
          ))}
      </div>

      <Card>
        <CardContent className="p-4 sm:p-5">
          {tab === "environments" && (
            <div className="space-y-4">
              {can(role, "manager") && !p.is_archived && p.environment_count > 0 && (
                <div className="flex justify-end">
                  <Button onClick={() => setEnvOpen(true)}>
                    <Plus /> Thêm môi trường
                  </Button>
                </div>
              )}
              <EnvironmentsTable projectId={p.id} role={role} archived={p.is_archived} onCreate={() => setEnvOpen(true)} />
            </div>
          )}
          {tab === "members" && <MembersPanel projectId={p.id} role={role} archived={p.is_archived} />}
          {tab === "audit" && can(role, "manager") && <AuditPanel projectId={p.id} />}
        </CardContent>
      </Card>

      <EditProjectDialog project={p} open={editing} onOpenChange={setEditing} />
      <EnvironmentFormDialog open={envOpen} onOpenChange={setEnvOpen} projectId={p.id} role={role} />
      <ConfirmDialog
        open={confirmArchive}
        onOpenChange={setConfirmArchive}
        title={`Lưu trữ dự án ${p.name}?`}
        description="Dự án sẽ ẩn khỏi danh sách và chuyển sang chỉ xem. Dữ liệu không bị xóa, Admin có thể khôi phục."
        confirmLabel="Lưu trữ"
        loading={archive.isPending}
        onConfirm={() => archive.mutate(false)}
      />
    </>
  );
}
