import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Ban } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { api, type Run } from "@/lib/api";
import { isActive } from "@/lib/status";

/** Thanh tiến độ theo số test case đã có kết quả, chia màu theo trạng thái. */
export function RunProgress({ run }: { run: Run }) {
  const done = run.passed + run.failed + run.skipped + run.blocked + run.errored + run.cancelled;
  const pct = (n: number) => (run.total ? `${(n / run.total) * 100}%` : "0%");
  return (
    <div className="grid gap-1">
      <div
        className="flex h-2 w-full overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-label="Tiến độ lần chạy"
        aria-valuemin={0}
        aria-valuemax={run.total}
        aria-valuenow={done}
      >
        <div className="bg-status-passed" style={{ width: pct(run.passed) }} />
        <div className="bg-status-failed" style={{ width: pct(run.failed + run.errored) }} />
        <div className="bg-status-blocked" style={{ width: pct(run.blocked) }} />
        <div className="bg-status-skipped" style={{ width: pct(run.skipped) }} />
        <div className="bg-status-cancelled" style={{ width: pct(run.cancelled) }} />
      </div>
      <p className="text-xs tabular-nums text-muted-foreground">
        {done}/{run.total} xong · {run.passed} đạt · {run.failed + run.errored} lỗi
        {run.blocked > 0 && ` · ${run.blocked} bị chặn`}
        {run.cancelled > 0 && ` · ${run.cancelled} đã hủy`}
      </p>
    </div>
  );
}

export function CancelRunButton({ run, size = "sm" }: { run: Run; size?: "sm" | "default" }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const m = useMutation({
    mutationFn: () => api<Run>(`/api/runs/${run.id}/cancel`, { method: "POST" }),
    onSuccess: (r) => {
      toast.success(r.status === "cancelled" ? "Đã hủy lần chạy" : "Đã gửi yêu cầu hủy, đang dừng sau bước hiện tại");
      void qc.invalidateQueries({ queryKey: ["runs"] });
      void qc.invalidateQueries({ queryKey: ["run", run.id] });
      void qc.invalidateQueries({ queryKey: ["active-runs"] });
      setOpen(false);
    },
    onError: (e) => toast.error(e.message),
  });
  if (!isActive(run.status)) return null;
  return (
    <>
      <Button variant="outline" size={size} disabled={run.cancel_requested} onClick={() => setOpen(true)}>
        <Ban /> {run.cancel_requested ? "Đang hủy..." : "Hủy"}
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Hủy lần chạy?"
        description="Bước đang chạy được hoàn tất an toàn rồi dừng; các test case chưa chạy sẽ ở trạng thái Đã hủy."
        confirmLabel="Hủy lần chạy"
        loading={m.isPending}
        onConfirm={() => m.mutate()}
      />
    </>
  );
}
