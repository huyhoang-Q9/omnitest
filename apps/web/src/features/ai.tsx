import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useAIStatus } from "@/hooks/ai";
import { api, type FailureAnalysis, type Project } from "@/lib/api";
import { AI_CATEGORY_LABEL, UNCERTAINTY_LABEL } from "@/lib/ai-labels";

/** Công tắc bật AI cho dự án (chỉ Admin dự án). */
export function ProjectAIToggle({ project, canEdit }: { project: Project; canEdit: boolean }) {
  const qc = useQueryClient();
  const status = useAIStatus();
  const m = useMutation({
    mutationFn: (enabled: boolean) => api<Project>(`/api/projects/${project.id}`, { method: "PATCH", json: { ai_enabled: enabled } }),
    onSuccess: (p) => {
      qc.setQueryData(["project", p.id], p);
      void qc.invalidateQueries({ queryKey: ["projects"] });
      toast.success(p.ai_enabled ? "Đã bật AI cho dự án" : "Đã tắt AI cho dự án");
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <div className="mb-5 flex items-start gap-3 rounded-lg border px-4 py-3 text-sm">
      <Switch
        id="project-ai"
        checked={project.ai_enabled}
        disabled={!canEdit || project.is_archived || m.isPending}
        onCheckedChange={(v) => m.mutate(v)}
        aria-describedby="project-ai-help"
      />
      <div className="min-w-0 space-y-0.5">
        <Label htmlFor="project-ai">Cho phép dùng Trợ lý AI trong dự án</Label>
        <p id="project-ai-help" className="text-muted-foreground">
          Khi bật, yêu cầu nghiệp vụ và log lỗi (đã che secret) của dự án được gửi tới nhà cung cấp AI do máy chủ cấu hình.
          {!canEdit && " Chỉ Admin dự án được thay đổi."}
          {status.data && !status.data.configured && " Máy chủ hiện chưa cấu hình AI nên chức năng AI chưa dùng được."}
        </p>
      </div>
    </div>
  );
}

/** Nút và kết quả phân tích lỗi bằng AI cho một test case không đạt. */
export function AnalyzeFailure({ itemId, enabled }: { itemId: string; enabled: boolean }) {
  const [result, setResult] = useState<FailureAnalysis | null>(null);
  const m = useMutation({
    mutationFn: () => api<FailureAnalysis>(`/api/run-items/${itemId}/ai/analyze`, { method: "POST" }),
    onSuccess: setResult,
    onError: (e) => toast.error(e.message),
  });
  if (!enabled) return null;
  return (
    <div className="grid gap-2">
      {!result && (
        <Button variant="outline" size="sm" className="w-fit" loading={m.isPending} onClick={() => m.mutate()}>
          <Sparkles /> Phân tích lỗi bằng AI
        </Button>
      )}
      {result && (
        <div className="grid gap-2 rounded-md border border-primary/30 bg-primary/5 p-3 text-sm" role="region" aria-label="Phân tích của AI">
          <div className="flex flex-wrap items-center gap-2">
            <Sparkles className="size-4" />
            <span className="font-medium">Phân tích của AI (tham khảo, cần người kiểm tra lại)</span>
            <Badge variant="outline">{AI_CATEGORY_LABEL[result.category]}</Badge>
            <Badge variant={result.confidence === "high" ? "default" : "warning"}>Độ tin cậy: {UNCERTAINTY_LABEL[result.confidence]}</Badge>
          </div>
          <p>{result.summary}</p>
          <p>
            <span className="font-medium">Nguyên nhân khả dĩ: </span>
            {result.probable_cause}
          </p>
          <AIList title="Căn cứ" items={result.evidence} />
          <AIList title="Gợi ý xử lý" items={result.suggestions} />
          <AIList title="Giả định" items={result.assumptions} />
          <p className="text-xs text-muted-foreground">Mô hình: {result.model}</p>
        </div>
      )}
    </div>
  );
}

export function AIList({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div>
      <p className="font-medium">{title}</p>
      <ul className="list-disc space-y-0.5 pl-5">
        {items.map((x, i) => (
          <li key={i} className="break-words">
            {x}
          </li>
        ))}
      </ul>
    </div>
  );
}
