import { STATUS_META, type RunStatus } from "@/lib/status";
import { cn } from "@/lib/utils";

export function StatusBadge({ status }: { status: RunStatus }) {
  const meta = STATUS_META[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium", meta.className)}>
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {meta.label}
    </span>
  );
}
