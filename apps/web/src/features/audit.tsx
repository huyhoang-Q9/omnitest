import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Pagination } from "@/components/pagination";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, type AuditEntry, type Page } from "@/lib/api";
import { auditLabel, auditSummary } from "@/lib/audit-labels";
import { formatDateTime } from "@/lib/utils";

const PAGE_SIZE = 25;

export function AuditPanel({ projectId }: { projectId: string }) {
  const [page, setPage] = useState(1);
  const q = useQuery({
    queryKey: ["audit", projectId, page],
    queryFn: () => api<Page<AuditEntry>>(`/api/projects/${projectId}/audit-logs?page=${page}&page_size=${PAGE_SIZE}`),
    placeholderData: keepPreviousData,
  });
  if (q.isPending) return <LoadingState />;
  if (q.isError) return <ErrorState message={q.error.message} onRetry={() => q.refetch()} />;
  if (q.data.items.length === 0) return <EmptyState title="Chưa có nhật ký" />;
  return (
    <>
      <Table>
        <THead>
          <TR>
            <TH>Thời gian</TH>
            <TH>Thao tác</TH>
            <TH className="hidden md:table-cell">Người thực hiện</TH>
          </TR>
        </THead>
        <TBody>
          {q.data.items.map((a) => (
            <TR key={a.id}>
              <TD className="whitespace-nowrap text-muted-foreground">{formatDateTime(a.created_at)}</TD>
              <TD>
                <span className="font-medium">{auditLabel(a.action)}</span>
                {auditSummary(a.details) && <span className="text-muted-foreground"> · {auditSummary(a.details)}</span>}
                <span className="block text-xs text-muted-foreground md:hidden">{a.actor_email}</span>
              </TD>
              <TD className="hidden md:table-cell">{a.actor_email ?? "Hệ thống"}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
      <Pagination page={page} pageSize={PAGE_SIZE} total={q.data.total} onPageChange={setPage} />
    </>
  );
}
