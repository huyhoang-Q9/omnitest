import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus } from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { FormField } from "@/components/form-field";
import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useMe } from "@/hooks/auth";
import { api, type User } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

const userSchema = z.object({
  email: z.string().trim().email("Email không hợp lệ"),
  full_name: z.string().trim().min(1, "Vui lòng nhập họ tên").max(200),
  password: z
    .string()
    .min(10, "Ít nhất 10 ký tự")
    .refine((v) => /[a-z]/.test(v) && /[A-Z]/.test(v), "Cần cả chữ hoa và chữ thường")
    .refine((v) => /\d/.test(v), "Cần ít nhất một chữ số"),
  is_system_admin: z.boolean(),
});
type UserValues = z.infer<typeof userSchema>;

function CreateUserDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const form = useForm<UserValues>({
    resolver: zodResolver(userSchema),
    defaultValues: { email: "", full_name: "", password: "", is_system_admin: false },
  });
  const m = useMutation({
    mutationFn: (v: UserValues) => api<User>("/api/users", { method: "POST", json: v }),
    onSuccess: (u) => {
      toast.success(`Đã tạo tài khoản ${u.email}`);
      void qc.invalidateQueries({ queryKey: ["users"] });
      form.reset();
      onOpenChange(false);
    },
    onError: (e) => toast.error(e.message),
  });
  const { errors } = form.formState;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Tạo tài khoản</DialogTitle>
          <DialogDescription>Gửi mật khẩu ban đầu cho người dùng qua kênh an toàn.</DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={form.handleSubmit((v) => m.mutate(v))} noValidate>
          <FormField id="u-email" label="Email" required error={errors.email?.message}>
            <Input id="u-email" type="email" autoComplete="off" {...form.register("email")} />
          </FormField>
          <FormField id="u-name" label="Họ tên" required error={errors.full_name?.message}>
            <Input id="u-name" {...form.register("full_name")} />
          </FormField>
          <FormField
            id="u-pass"
            label="Mật khẩu ban đầu"
            required
            error={errors.password?.message}
            hint="Ít nhất 10 ký tự, có chữ hoa, chữ thường và chữ số."
          >
            <Input id="u-pass" type="password" autoComplete="new-password" {...form.register("password")} />
          </FormField>
          <label className="flex items-center justify-between gap-4 rounded-lg border p-3 text-sm">
            <span>
              <span className="font-medium">Quản trị hệ thống</span>
              <span className="block text-xs text-muted-foreground">Tạo dự án, quản lý người dùng, thấy mọi dự án.</span>
            </span>
            <Controller
              control={form.control}
              name="is_system_admin"
              render={({ field }) => <Switch checked={field.value} onCheckedChange={field.onChange} />}
            />
          </label>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Hủy
            </Button>
            <Button type="submit" loading={m.isPending}>
              Tạo tài khoản
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function UsersCard() {
  const [open, setOpen] = useState(false);
  const q = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/api/users") });
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>Người dùng</CardTitle>
          <CardDescription>Chỉ quản trị hệ thống thấy mục này.</CardDescription>
        </div>
        <Button size="sm" onClick={() => setOpen(true)}>
          <UserPlus /> Tạo tài khoản
        </Button>
      </CardHeader>
      <CardContent>
        {q.isPending && <LoadingState />}
        {q.isError && <ErrorState message={q.error.message} onRetry={() => q.refetch()} />}
        {q.data && (
          <Table>
            <THead>
              <TR>
                <TH>Người dùng</TH>
                <TH>Quyền</TH>
                <TH className="hidden md:table-cell">Đăng nhập gần nhất</TH>
              </TR>
            </THead>
            <TBody>
              {q.data.map((u) => (
                <TR key={u.id}>
                  <TD>
                    <p className="font-medium">{u.full_name}</p>
                    <p className="text-xs text-muted-foreground">{u.email}</p>
                  </TD>
                  <TD>
                    <div className="flex flex-wrap gap-1">
                      {u.is_system_admin ? <Badge>Quản trị hệ thống</Badge> : <Badge variant="outline">Người dùng</Badge>}
                      {!u.is_active && <Badge variant="danger">Đã khóa</Badge>}
                    </div>
                  </TD>
                  <TD className="hidden text-muted-foreground md:table-cell">{formatDateTime(u.last_login_at)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardContent>
      <CreateUserDialog open={open} onOpenChange={setOpen} />
    </Card>
  );
}

export function SettingsPage() {
  const { data: me } = useMe();
  if (!me) return null;
  return (
    <>
      <PageHeader title="Cài đặt" description="Tài khoản và quản trị hệ thống." />
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Tài khoản của bạn</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 text-sm sm:grid-cols-3">
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Họ tên</p>
              <p className="font-medium">{me.full_name}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Email</p>
              <p className="font-medium">{me.email}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Ngôn ngữ giao diện</p>
              <p className="font-medium">Tiếng Việt</p>
            </div>
          </CardContent>
        </Card>
        {me.is_system_admin && <UsersCard />}
      </div>
    </>
  );
}
