import { zodResolver } from "@hookform/resolvers/zod";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, FolderKanban, Plus, Search } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";
import { FormField } from "@/components/form-field";
import { PageHeader } from "@/components/page-header";
import { Pagination } from "@/components/pagination";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useMe } from "@/hooks/auth";
import { useDebounced } from "@/hooks/use-debounced";
import { api, ROLE_LABEL, type Page, type Project } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

const PAGE_SIZE = 20;

const createSchema = z.object({
  key: z
    .string()
    .trim()
    .toUpperCase()
    .regex(/^[A-Z][A-Z0-9]{1,15}$/, "2 đến 16 ký tự A-Z, 0-9, bắt đầu bằng chữ cái"),
  name: z.string().trim().min(1, "Vui lòng nhập tên dự án").max(200),
  description: z.string().max(5000),
});
type CreateValues = z.infer<typeof createSchema>;

function CreateProjectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const form = useForm<CreateValues>({ resolver: zodResolver(createSchema), defaultValues: { key: "", name: "", description: "" } });
  const m = useMutation({
    mutationFn: (v: CreateValues) => api<Project>("/api/projects", { method: "POST", json: v }),
    onSuccess: (p) => {
      toast.success(`Đã tạo dự án ${p.name}`);
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      form.reset();
      onOpenChange(false);
      navigate(`/projects/${p.id}`);
    },
    onError: (e) => toast.error(e.message),
  });
  const { errors } = form.formState;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Tạo dự án</DialogTitle>
          <DialogDescription>Bạn sẽ là Admin của dự án mới.</DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={form.handleSubmit((v) => m.mutate(v))} noValidate>
          <FormField id="p-key" label="Mã dự án" required error={errors.key?.message} hint="Dùng làm tiền tố mã test case, VD SHOP-TC-0001.">
            <Input id="p-key" placeholder="SHOP" aria-invalid={!!errors.key} {...form.register("key")} />
          </FormField>
          <FormField id="p-name" label="Tên dự án" required error={errors.name?.message}>
            <Input id="p-name" aria-invalid={!!errors.name} {...form.register("name")} />
          </FormField>
          <FormField id="p-desc" label="Mô tả" error={errors.description?.message}>
            <Textarea id="p-desc" {...form.register("description")} />
          </FormField>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Hủy
            </Button>
            <Button type="submit" loading={m.isPending}>
              Tạo dự án
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ProjectsPage() {
  const { data: me } = useMe();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [archived, setArchived] = useState(false);
  const [page, setPage] = useState(1);
  const q = useDebounced(search.trim());
  const createOpen = params.get("new") === "1";
  const setCreateOpen = (o: boolean) => setParams(o ? { new: "1" } : {}, { replace: true });

  const query = useQuery({
    queryKey: ["projects", { q, archived, page }],
    queryFn: () =>
      api<Page<Project>>(
        `/api/projects?${new URLSearchParams({ q, include_archived: String(archived), page: String(page), page_size: String(PAGE_SIZE) })}`,
      ),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        title="Dự án"
        description="Các dự án bạn tham gia và vai trò của bạn trong từng dự án."
        actions={
          me?.is_system_admin && (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus /> Tạo dự án
            </Button>
          )
        }
      />
      <Card className="p-4 sm:p-5">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative w-full sm:max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label="Tìm dự án"
              placeholder="Tìm theo tên hoặc mã"
              className="pl-9"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Switch
              checked={archived}
              onCheckedChange={(v) => {
                setArchived(v);
                setPage(1);
              }}
            />
            Hiện dự án đã lưu trữ
          </label>
        </div>

        {query.isPending && <LoadingState />}
        {query.isError && <ErrorState message={query.error.message} onRetry={() => query.refetch()} />}
        {query.data &&
          (query.data.items.length === 0 ? (
            <EmptyState
              icon={<FolderKanban className="size-6" />}
              title={q ? "Không có dự án phù hợp" : "Chưa có dự án nào"}
              description={q ? "Thử từ khóa khác." : me?.is_system_admin ? "Tạo dự án đầu tiên để bắt đầu." : "Bạn chưa được thêm vào dự án nào."}
            />
          ) : (
            <>
              <Table>
                <THead>
                  <TR>
                    <TH>Dự án</TH>
                    <TH>Vai trò</TH>
                    <TH className="hidden md:table-cell">Môi trường</TH>
                    <TH className="hidden md:table-cell">Thành viên</TH>
                    <TH className="hidden lg:table-cell">Cập nhật</TH>
                  </TR>
                </THead>
                <TBody>
                  {query.data.items.map((p) => (
                    <TR key={p.id}>
                      <TD>
                        <Link to={`/projects/${p.id}`} className="group flex items-center gap-3">
                          <span className="grid size-9 shrink-0 place-items-center rounded-md bg-accent text-xs font-semibold text-accent-foreground">
                            {p.key.slice(0, 3)}
                          </span>
                          <span className="min-w-0">
                            <span className="block truncate font-medium group-hover:underline">{p.name}</span>
                            <span className="flex items-center gap-2 text-xs text-muted-foreground">
                              {p.key}
                              {p.is_archived && (
                                <Badge variant="muted">
                                  <Archive className="size-3" /> Lưu trữ
                                </Badge>
                              )}
                            </span>
                          </span>
                        </Link>
                      </TD>
                      <TD>{p.my_role && <Badge variant="outline">{ROLE_LABEL[p.my_role]}</Badge>}</TD>
                      <TD className="hidden tabular-nums md:table-cell">{p.environment_count}</TD>
                      <TD className="hidden tabular-nums md:table-cell">{p.member_count}</TD>
                      <TD className="hidden text-muted-foreground lg:table-cell">{formatDateTime(p.updated_at)}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <Pagination page={page} pageSize={PAGE_SIZE} total={query.data.total} onPageChange={setPage} />
            </>
          ))}
      </Card>
      {me?.is_system_admin && <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />}
    </>
  );
}
