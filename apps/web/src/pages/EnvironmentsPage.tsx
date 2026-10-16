import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EnvironmentFormDialog, EnvironmentsTable } from "@/features/environments";
import { api, can, type Page, type Project } from "@/lib/api";

export function EnvironmentsPage() {
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["projects", { all: true }],
    queryFn: () => api<Page<Project>>("/api/projects?page_size=100"),
  });
  const projects = q.data?.items ?? [];
  const selected = projects.find((p) => p.id === params.get("project")) ?? projects[0];

  return (
    <>
      <PageHeader
        title="Môi trường"
        description="Dev, Test, UAT, Staging của từng dự án: base URL, host được phép và biến."
        actions={
          selected &&
          can(selected.my_role, "manager") && (
            <Button onClick={() => setOpen(true)}>
              <Plus /> Thêm môi trường
            </Button>
          )
        }
      />
      {q.isPending && <LoadingState />}
      {q.isError && <ErrorState message={q.error.message} onRetry={() => q.refetch()} />}
      {q.data &&
        (projects.length === 0 ? (
          <EmptyState title="Chưa có dự án" description="Môi trường thuộc về dự án. Hãy tạo hoặc được thêm vào một dự án trước." />
        ) : (
          <Card>
            <CardContent className="space-y-4 p-4 sm:p-5">
              <div className="grid max-w-sm gap-1.5">
                <Label htmlFor="env-project">Dự án</Label>
                <NativeSelect
                  id="env-project"
                  value={selected?.id}
                  onChange={(e) => setParams({ project: e.target.value }, { replace: true })}
                >
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.key} · {p.name}
                    </option>
                  ))}
                </NativeSelect>
              </div>
              {selected && <EnvironmentsTable projectId={selected.id} role={selected.my_role} onCreate={() => setOpen(true)} />}
            </CardContent>
          </Card>
        ))}
      {selected && <EnvironmentFormDialog open={open} onOpenChange={setOpen} projectId={selected.id} role={selected.my_role} />}
    </>
  );
}
