import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, Plus, Server, ShieldAlert } from "lucide-react";
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";
import { FormField } from "@/components/form-field";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, can, ENV_KIND_LABEL, type Environment, type EnvironmentKind, type ProjectRole } from "@/lib/api";

const KINDS = Object.keys(ENV_KIND_LABEL) as EnvironmentKind[];

const envSchema = z.object({
  name: z.string().trim().min(1, "Vui lòng nhập tên").max(100),
  kind: z.enum(["dev", "test", "uat", "staging"]),
  base_url: z
    .string()
    .trim()
    .refine((v) => {
      try {
        const u = new URL(v);
        return (u.protocol === "http:" || u.protocol === "https:") && !!u.hostname;
      } catch {
        return false;
      }
    }, "URL phải bắt đầu bằng http:// hoặc https://"),
  description: z.string().max(5000),
  allowed_hosts_text: z.string(),
  allow_private_network: z.boolean(),
  requires_run_confirmation: z.boolean(),
});
type EnvValues = z.infer<typeof envSchema>;

export function EnvironmentFormDialog({
  open,
  onOpenChange,
  projectId,
  environment,
  role,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  projectId: string;
  environment?: Environment;
  role: ProjectRole | null | undefined;
}) {
  const qc = useQueryClient();
  const isAdmin = can(role, "admin");
  const form = useForm<EnvValues>({ resolver: zodResolver(envSchema) });
  useEffect(() => {
    if (open)
      form.reset({
        name: environment?.name ?? "",
        kind: environment?.kind ?? "dev",
        base_url: environment?.base_url ?? "https://",
        description: environment?.description ?? "",
        allowed_hosts_text: (environment?.allowed_hosts ?? []).join("\n"),
        allow_private_network: environment?.allow_private_network ?? false,
        requires_run_confirmation: environment?.requires_run_confirmation ?? false,
      });
  }, [open, environment, form]);

  const m = useMutation({
    mutationFn: (v: EnvValues) => {
      const body = {
        name: v.name,
        kind: v.kind,
        base_url: v.base_url,
        description: v.description,
        allowed_hosts: v.allowed_hosts_text.split(/[\s,]+/).filter(Boolean),
        requires_run_confirmation: v.requires_run_confirmation,
        ...(isAdmin ? { allow_private_network: v.allow_private_network } : {}),
      };
      return environment
        ? api<Environment>(`/api/environments/${environment.id}`, { method: "PATCH", json: body })
        : api<Environment>(`/api/projects/${projectId}/environments`, { method: "POST", json: body });
    },
    onSuccess: (env) => {
      toast.success(environment ? "Đã cập nhật môi trường" : `Đã tạo môi trường ${env.name}`);
      void qc.invalidateQueries({ queryKey: ["environments"] });
      void qc.invalidateQueries({ queryKey: ["environment", env.id] });
      void qc.invalidateQueries({ queryKey: ["project", projectId] });
      onOpenChange(false);
    },
    onError: (e) => toast.error(e.message),
  });

  const { errors } = form.formState;
  const kind = form.watch("kind");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{environment ? "Sửa môi trường" : "Thêm môi trường"}</DialogTitle>
          <DialogDescription>Khai báo nơi chạy test. Thông tin đăng nhập hãy lưu thành biến secret, không đưa vào URL.</DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={form.handleSubmit((v) => m.mutate(v))} noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField id="e-name" label="Tên" required error={errors.name?.message}>
              <Input id="e-name" placeholder="UAT nội bộ" aria-invalid={!!errors.name} {...form.register("name")} />
            </FormField>
            <FormField id="e-kind" label="Loại" required>
              <NativeSelect
                id="e-kind"
                {...form.register("kind", {
                  onChange: (e) =>
                    !environment && form.setValue("requires_run_confirmation", ["uat", "staging"].includes(e.target.value)),
                })}
              >
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {ENV_KIND_LABEL[k]}
                  </option>
                ))}
              </NativeSelect>
            </FormField>
          </div>
          <FormField
            id="e-url"
            label="Base URL"
            required
            error={errors.base_url?.message}
            hint="Với test Desktop/Mobile: địa chỉ Appium server, VD http://appium-host:4723. Appium ở mạng nội bộ thì cần Admin bật cho phép mạng nội bộ."
          >
            <Input id="e-url" inputMode="url" aria-invalid={!!errors.base_url} {...form.register("base_url")} />
          </FormField>
          <FormField
            id="e-hosts"
            label="Host đích được phép"
            hint="Mỗi dòng một host, VD api.shop.vn hoặc *.shop.vn. Dùng để chặn gọi tới đích lạ khi chạy test."
          >
            <Textarea id="e-hosts" rows={3} {...form.register("allowed_hosts_text")} />
          </FormField>
          <FormField id="e-desc" label="Mô tả">
            <Textarea id="e-desc" rows={2} {...form.register("description")} />
          </FormField>
          <div className="space-y-3 rounded-lg border p-3">
            <label className="flex items-start justify-between gap-4 text-sm">
              <span>
                <span className="font-medium">Xác nhận trước khi chạy test</span>
                <span className="block text-xs text-muted-foreground">
                  Khuyến nghị cho UAT/Staging{kind === "uat" || kind === "staging" ? " (đang là mặc định)" : ""}.
                </span>
              </span>
              <Controller
                control={form.control}
                name="requires_run_confirmation"
                render={({ field }) => <Switch checked={field.value} onCheckedChange={field.onChange} />}
              />
            </label>
            <label className="flex items-start justify-between gap-4 text-sm">
              <span>
                <span className="flex items-center gap-1.5 font-medium">
                  <ShieldAlert className="size-4 text-status-blocked" /> Cho phép đích mạng nội bộ
                </span>
                <span className="block text-xs text-muted-foreground">
                  {isAdmin
                    ? "Chỉ bật khi hệ thống cần test nằm trong mạng nội bộ. Địa chỉ metadata cloud luôn bị chặn."
                    : "Chỉ Admin dự án được thay đổi."}
                </span>
              </span>
              <Controller
                control={form.control}
                name="allow_private_network"
                render={({ field }) => <Switch checked={field.value} onCheckedChange={field.onChange} disabled={!isAdmin} />}
              />
            </label>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Hủy
            </Button>
            <Button type="submit" loading={m.isPending}>
              {environment ? "Lưu thay đổi" : "Thêm môi trường"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function EnvKindBadge({ kind }: { kind: EnvironmentKind }) {
  const variant = kind === "staging" || kind === "uat" ? "warning" : "default";
  return <Badge variant={variant}>{ENV_KIND_LABEL[kind]}</Badge>;
}

export function EnvironmentsTable({
  projectId,
  role,
  archived,
  onCreate,
}: {
  projectId: string;
  role: ProjectRole | null | undefined;
  archived?: boolean;
  onCreate?: () => void;
}) {
  const q = useQuery({
    queryKey: ["environments", projectId],
    queryFn: () => api<Environment[]>(`/api/projects/${projectId}/environments`),
  });
  if (q.isPending) return <LoadingState />;
  if (q.isError) return <ErrorState message={q.error.message} onRetry={() => q.refetch()} />;
  if (q.data.length === 0)
    return (
      <EmptyState
        icon={<Server className="size-6" />}
        title="Chưa có môi trường"
        description="Thêm Dev, Test, UAT hoặc Staging để khai báo base URL và biến dùng khi chạy test."
        action={
          can(role, "manager") &&
          !archived &&
          onCreate && (
            <Button onClick={onCreate}>
              <Plus /> Thêm môi trường
            </Button>
          )
        }
      />
    );
  return (
    <Table>
      <THead>
        <TR>
          <TH>Môi trường</TH>
          <TH>Base URL</TH>
          <TH className="hidden md:table-cell">Biến</TH>
          <TH className="hidden md:table-cell">Bảo vệ</TH>
        </TR>
      </THead>
      <TBody>
        {q.data.map((e) => (
          <TR key={e.id}>
            <TD>
              <Link to={`/environments/${e.id}`} className="flex items-center gap-2 font-medium hover:underline">
                {e.name} <EnvKindBadge kind={e.kind} />
              </Link>
            </TD>
            <TD className="max-w-[16rem] truncate font-mono text-xs">{e.base_url}</TD>
            <TD className="hidden tabular-nums md:table-cell">{e.variable_count}</TD>
            <TD className="hidden md:table-cell">
              <div className="flex flex-wrap gap-1">
                {e.requires_run_confirmation && (
                  <Badge variant="muted">
                    <Lock className="size-3" /> Cần xác nhận
                  </Badge>
                )}
                {e.allow_private_network && <Badge variant="warning">Mạng nội bộ</Badge>}
              </div>
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
