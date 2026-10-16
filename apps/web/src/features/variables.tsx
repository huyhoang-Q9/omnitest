import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Lock, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { FormField } from "@/components/form-field";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, type Variable } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

const schema = z.object({
  key: z
    .string()
    .trim()
    .regex(/^[A-Z_][A-Z0-9_]{0,99}$/, "Chỉ gồm A-Z, 0-9, dấu gạch dưới, không bắt đầu bằng số"),
  value: z.string().max(10000),
  is_secret: z.boolean(),
  description: z.string().max(1000),
});
type Values = z.infer<typeof schema>;

function VariableDialog({
  environmentId,
  variable,
  open,
  onOpenChange,
}: {
  environmentId: string;
  variable?: Variable;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const qc = useQueryClient();
  const form = useForm<Values>({ resolver: zodResolver(schema) });
  useEffect(() => {
    if (open)
      form.reset({
        key: variable?.key ?? "",
        value: variable && !variable.is_secret ? (variable.value ?? "") : "",
        is_secret: variable?.is_secret ?? false,
        description: variable?.description ?? "",
      });
  }, [open, variable, form]);
  const isSecret = form.watch("is_secret");

  const m = useMutation({
    mutationFn: (v: Values) => {
      if (!variable) return api<Variable>(`/api/environments/${environmentId}/variables`, { method: "POST", json: v });
      // Secret để trống giá trị nghĩa là giữ nguyên giá trị cũ.
      const value = variable.is_secret && v.value === "" ? null : v.value;
      return api<Variable>(`/api/environments/${environmentId}/variables/${variable.id}`, {
        method: "PATCH",
        json: { value, description: v.description },
      });
    },
    onSuccess: () => {
      toast.success(variable ? "Đã cập nhật biến" : "Đã thêm biến");
      void qc.invalidateQueries({ queryKey: ["variables", environmentId] });
      void qc.invalidateQueries({ queryKey: ["environment", environmentId] });
      onOpenChange(false);
    },
    onError: (e) => toast.error(e.message),
  });

  const { errors } = form.formState;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{variable ? `Sửa biến ${variable.key}` : "Thêm biến"}</DialogTitle>
          <DialogDescription>
            Biến secret được mã hóa khi lưu và không bao giờ hiển thị lại, kể cả với Admin.
          </DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={form.handleSubmit((v) => m.mutate(v))} noValidate>
          <FormField id="v-key" label="Tên biến" required error={errors.key?.message}>
            <Input
              id="v-key"
              className="font-mono"
              placeholder="API_TOKEN"
              disabled={!!variable}
              aria-invalid={!!errors.key}
              {...form.register("key", { setValueAs: (v: string) => v.toUpperCase() })}
            />
          </FormField>
          <label className="flex items-center justify-between gap-4 rounded-lg border p-3 text-sm">
            <span>
              <span className="flex items-center gap-1.5 font-medium">
                <Lock className="size-4" /> Secret
              </span>
              <span className="block text-xs text-muted-foreground">Mật khẩu, token, API key. Không đổi được sau khi tạo.</span>
            </span>
            <Controller
              control={form.control}
              name="is_secret"
              render={({ field }) => <Switch checked={field.value} onCheckedChange={field.onChange} disabled={!!variable} />}
            />
          </label>
          <FormField
            id="v-value"
            label="Giá trị"
            hint={variable?.is_secret ? "Để trống nếu muốn giữ giá trị hiện tại." : undefined}
          >
            <Input
              id="v-value"
              type={isSecret ? "password" : "text"}
              autoComplete="off"
              className="font-mono"
              placeholder={variable?.is_secret ? "••••••••" : ""}
              {...form.register("value")}
            />
          </FormField>
          <FormField id="v-desc" label="Mô tả">
            <Input id="v-desc" {...form.register("description")} />
          </FormField>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Hủy
            </Button>
            <Button type="submit" loading={m.isPending}>
              {variable ? "Lưu" : "Thêm biến"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function VariablesPanel({ environmentId, canEdit }: { environmentId: string; canEdit: boolean }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<Variable | "new" | null>(null);
  const [deleting, setDeleting] = useState<Variable | null>(null);
  const q = useQuery({
    queryKey: ["variables", environmentId],
    queryFn: () => api<Variable[]>(`/api/environments/${environmentId}/variables`),
  });
  const del = useMutation({
    mutationFn: (id: string) => api<void>(`/api/environments/${environmentId}/variables/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Đã xóa biến");
      setDeleting(null);
      void qc.invalidateQueries({ queryKey: ["variables", environmentId] });
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <div className="space-y-4">
      {canEdit && q.data && q.data.length > 0 && (
        <div className="flex justify-end">
          <Button onClick={() => setEditing("new")}>
            <Plus /> Thêm biến
          </Button>
        </div>
      )}
      {q.isPending && <LoadingState />}
      {q.isError && <ErrorState message={q.error.message} onRetry={() => q.refetch()} />}
      {q.data &&
        (q.data.length === 0 ? (
          <EmptyState
            icon={<KeyRound className="size-6" />}
            title="Chưa có biến"
            description="Khai báo biến môi trường như tài khoản test, token, timeout để dùng khi chạy test."
            action={
              canEdit && (
                <Button onClick={() => setEditing("new")}>
                  <Plus /> Thêm biến
                </Button>
              )
            }
          />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Tên biến</TH>
                <TH>Giá trị</TH>
                <TH className="hidden md:table-cell">Mô tả</TH>
                <TH className="hidden lg:table-cell">Cập nhật</TH>
                {canEdit && <TH className="w-24" />}
              </TR>
            </THead>
            <TBody>
              {q.data.map((v) => (
                <TR key={v.id}>
                  <TD className="font-mono text-xs font-medium">{v.key}</TD>
                  <TD>
                    {v.is_secret ? (
                      <Badge variant="muted">
                        <Lock className="size-3" /> {v.has_value ? "Đã đặt (ẩn)" : "Chưa đặt"}
                      </Badge>
                    ) : (
                      <span className="block max-w-[16rem] truncate font-mono text-xs">{v.value}</span>
                    )}
                  </TD>
                  <TD className="hidden text-muted-foreground md:table-cell">{v.description}</TD>
                  <TD className="hidden text-muted-foreground lg:table-cell">{formatDateTime(v.updated_at)}</TD>
                  {canEdit && (
                    <TD>
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="icon" aria-label={`Sửa ${v.key}`} onClick={() => setEditing(v)}>
                          <Pencil />
                        </Button>
                        <Button variant="ghost" size="icon" aria-label={`Xóa ${v.key}`} onClick={() => setDeleting(v)}>
                          <Trash2 className="text-status-failed" />
                        </Button>
                      </div>
                    </TD>
                  )}
                </TR>
              ))}
            </TBody>
          </Table>
        ))}
      <VariableDialog
        environmentId={environmentId}
        variable={editing && editing !== "new" ? editing : undefined}
        open={editing !== null}
        onOpenChange={(o) => !o && setEditing(null)}
      />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Xóa biến ${deleting?.key ?? ""}?`}
        description="Test đang dùng biến này sẽ không còn lấy được giá trị. Thao tác không hoàn tác được."
        confirmLabel="Xóa biến"
        loading={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting.id)}
      />
    </div>
  );
}
