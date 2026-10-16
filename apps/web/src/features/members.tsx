import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2, UserPlus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { FormField } from "@/components/form-field";
import { ErrorState, LoadingState } from "@/components/states";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, can, ROLE_LABEL, type Member, type ProjectRole } from "@/lib/api";

const ROLES: ProjectRole[] = ["admin", "manager", "tester", "viewer"];

const ROLE_HINT: Record<ProjectRole, string> = {
  admin: "Toàn quyền dự án, quản lý thành viên",
  manager: "Quản lý môi trường, biến, nội dung test",
  tester: "Xem và chạy test",
  viewer: "Chỉ xem",
};

export function MembersPanel({ projectId, role, archived }: { projectId: string; role: ProjectRole | null | undefined; archived: boolean }) {
  const qc = useQueryClient();
  const manage = can(role, "admin") && !archived;
  const [email, setEmail] = useState("");
  const [newRole, setNewRole] = useState<ProjectRole>("tester");
  const [removing, setRemoving] = useState<Member | null>(null);
  const q = useQuery({ queryKey: ["members", projectId], queryFn: () => api<Member[]>(`/api/projects/${projectId}/members`) });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["members", projectId] });
    void qc.invalidateQueries({ queryKey: ["project", projectId] });
  };

  const add = useMutation({
    mutationFn: () => api<Member>(`/api/projects/${projectId}/members`, { method: "POST", json: { email, role: newRole } }),
    onSuccess: (m) => {
      toast.success(`Đã thêm ${m.email}`);
      setEmail("");
      refresh();
    },
    onError: (e) => toast.error(e.message),
  });
  const update = useMutation({
    mutationFn: ({ id, r }: { id: string; r: ProjectRole }) =>
      api<Member>(`/api/projects/${projectId}/members/${id}`, { method: "PATCH", json: { role: r } }),
    onSuccess: () => {
      toast.success("Đã đổi vai trò");
      refresh();
    },
    onError: (e) => {
      toast.error(e.message);
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/api/projects/${projectId}/members/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Đã gỡ thành viên");
      setRemoving(null);
      refresh();
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <div className="space-y-4">
      {manage && (
        <form
          className="grid gap-3 rounded-lg border bg-muted/40 p-3 sm:grid-cols-[1fr_12rem_auto] sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            if (email.trim()) add.mutate();
          }}
        >
          <FormField id="m-email" label="Email người dùng">
            <Input id="m-email" type="email" placeholder="ten@congty.vn" value={email} onChange={(e) => setEmail(e.target.value)} />
          </FormField>
          <FormField id="m-role" label="Vai trò">
            <NativeSelect id="m-role" value={newRole} onChange={(e) => setNewRole(e.target.value as ProjectRole)}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </NativeSelect>
          </FormField>
          <Button type="submit" loading={add.isPending} disabled={!email.trim()}>
            <UserPlus /> Thêm
          </Button>
        </form>
      )}
      {q.isPending && <LoadingState />}
      {q.isError && <ErrorState message={q.error.message} onRetry={() => q.refetch()} />}
      {q.data && (
        <Table>
          <THead>
            <TR>
              <TH>Thành viên</TH>
              <TH>Vai trò</TH>
              {manage && <TH className="w-12" />}
            </TR>
          </THead>
          <TBody>
            {q.data.map((m) => (
              <TR key={m.id}>
                <TD>
                  <p className="font-medium">{m.full_name}</p>
                  <p className="text-xs text-muted-foreground">{m.email}</p>
                </TD>
                <TD>
                  {manage ? (
                    <NativeSelect
                      aria-label={`Vai trò của ${m.email}`}
                      className="max-w-[10rem]"
                      value={m.role}
                      disabled={update.isPending}
                      onChange={(e) => update.mutate({ id: m.id, r: e.target.value as ProjectRole })}
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {ROLE_LABEL[r]}
                        </option>
                      ))}
                    </NativeSelect>
                  ) : (
                    <Badge variant="outline" title={ROLE_HINT[m.role]}>
                      {ROLE_LABEL[m.role]}
                    </Badge>
                  )}
                </TD>
                {manage && (
                  <TD>
                    <Button variant="ghost" size="icon" aria-label={`Gỡ ${m.email}`} onClick={() => setRemoving(m)}>
                      <Trash2 className="text-status-failed" />
                    </Button>
                  </TD>
                )}
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      <ul className="grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
        {ROLES.map((r) => (
          <li key={r}>
            <span className="font-medium text-foreground">{ROLE_LABEL[r]}</span>: {ROLE_HINT[r]}
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(o) => !o && setRemoving(null)}
        title="Gỡ thành viên khỏi dự án?"
        description={`${removing?.email ?? ""} sẽ không còn truy cập được dự án này.`}
        confirmLabel="Gỡ thành viên"
        loading={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing.id)}
      />
    </div>
  );
}
