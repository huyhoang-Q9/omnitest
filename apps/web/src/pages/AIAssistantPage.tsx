import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { ProjectPicker } from "@/components/project-picker";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { NativeSelect, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AIList } from "@/features/ai";
import { useAIStatus } from "@/hooks/ai";
import { useProjectSelection } from "@/hooks/projects";
import { api, can, type AIDraft, type AISuggestion, type Project, type TestCase } from "@/lib/api";
import { UNCERTAINTY_LABEL } from "@/lib/ai-labels";
import { PRIORITY_LABEL } from "@/lib/test-labels";

function DraftCard({ draft, checked, onToggle }: { draft: AIDraft; checked: boolean; onToggle: () => void }) {
  const id = `draft-${draft.title}`;
  return (
    <li className="grid min-w-0 gap-2 rounded-md border p-3 text-sm">
      <div className="flex min-w-0 items-start gap-3">
        <input
          id={id}
          type="checkbox"
          className="mt-1 size-4 shrink-0"
          checked={checked}
          disabled={!draft.valid}
          onChange={onToggle}
        />
        <div className="min-w-0 flex-1 space-y-1">
          <label htmlFor={id} className="block font-medium break-words">
            {draft.title}
          </label>
          <div className="flex flex-wrap gap-1.5">
            <Badge variant="outline">{draft.test_type.toUpperCase()}</Badge>
            <Badge variant="outline">{PRIORITY_LABEL[draft.priority]}</Badge>
            <Badge variant={draft.uncertainty === "low" ? "muted" : "warning"}>Độ không chắc chắn: {UNCERTAINTY_LABEL[draft.uncertainty]}</Badge>
            {!draft.valid && <Badge variant="danger">Không hợp lệ, không lưu được</Badge>}
          </div>
          {draft.description && <p className="break-words text-muted-foreground">{draft.description}</p>}
          {draft.rationale && (
            <p className="break-words">
              <span className="font-medium">Lý do: </span>
              {draft.rationale}
            </p>
          )}
          <AIList title="Giả định" items={draft.assumptions} />
          <AIList title="Lỗi kiểm tra định nghĩa" items={draft.errors} />
          <details>
            <summary className="cursor-pointer text-muted-foreground">Xem định nghĩa các bước</summary>
            <pre className="mt-1 max-h-64 overflow-auto rounded bg-muted p-2 text-xs">{JSON.stringify(draft.definition, null, 2)}</pre>
          </details>
        </div>
      </div>
    </li>
  );
}

function Suggest({ project }: { project: Project }) {
  const qc = useQueryClient();
  const [requirement, setRequirement] = useState("");
  const [testType, setTestType] = useState<"api" | "web">("api");
  const [count, setCount] = useState(5);
  const [result, setResult] = useState<AISuggestion | null>(null);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const suggest = useMutation({
    mutationFn: () =>
      api<AISuggestion>(`/api/projects/${project.id}/ai/suggest-test-cases`, {
        method: "POST",
        json: { requirement, test_type: testType, count },
      }),
    onSuccess: (r) => {
      setResult(r);
      setPicked(new Set(r.drafts.flatMap((d, i) => (d.valid ? [i] : []))));
    },
    onError: (e) => toast.error(e.message),
  });
  const save = useMutation({
    mutationFn: async () => {
      const created: TestCase[] = [];
      for (const i of [...picked].sort((a, b) => a - b)) {
        const d = (result as AISuggestion).drafts[i];
        created.push(
          await api<TestCase>(`/api/projects/${project.id}/test-cases`, {
            method: "POST",
            json: {
              title: d.title,
              description: d.description,
              test_type: d.test_type,
              priority: d.priority,
              status: "draft",
              tags: [...(d.tags ?? []), "ai"].slice(0, 20),
              preconditions: d.preconditions,
              expected_result: d.expected_result,
              test_data: { source: "ai", assumptions: d.assumptions },
              definition: d.definition,
            },
          }),
        );
      }
      return created;
    },
    onSuccess: (created) => {
      toast.success(`Đã lưu ${created.length} test case ở trạng thái Nháp`);
      void qc.invalidateQueries({ queryKey: ["test-cases"] });
      setResult(null);
      setPicked(new Set());
    },
    onError: (e) => toast.error(e.message),
  });
  const toggle = (i: number) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  return (
    <Card>
      <CardContent className="grid gap-4 p-4 sm:p-5">
        <div className="grid gap-1.5">
          <Label htmlFor="ai-requirement">Mô tả yêu cầu hoặc chức năng cần test</Label>
          <Textarea
            id="ai-requirement"
            rows={6}
            maxLength={20000}
            value={requirement}
            onChange={(e) => setRequirement(e.target.value)}
            placeholder="VD: API POST /api/items tạo mặt hàng, yêu cầu Bearer token, tên bắt buộc 1 đến 100 ký tự, số lượng không âm..."
          />
          <p className="text-xs text-muted-foreground">Không dán mật khẩu, token hay dữ liệu cá nhân thật vào đây.</p>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="grid gap-1.5">
            <Label htmlFor="ai-type">Loại test</Label>
            <NativeSelect id="ai-type" value={testType} onChange={(e) => setTestType(e.target.value as "api" | "web")}>
              <option value="api">API</option>
              <option value="web">Web</option>
            </NativeSelect>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="ai-count">Số đề xuất tối đa</Label>
            <NativeSelect id="ai-count" value={count} onChange={(e) => setCount(Number(e.target.value))}>
              {[3, 5, 8, 10].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="flex items-end">
            <Button className="w-full" disabled={requirement.trim().length < 10} loading={suggest.isPending} onClick={() => suggest.mutate()}>
              <Sparkles /> Đề xuất test case
            </Button>
          </div>
        </div>
        {result && (
          <div className="grid gap-3" role="region" aria-label="Đề xuất của AI">
            <div className="rounded-md border border-status-blocked/30 bg-status-blocked/10 px-3 py-2 text-sm">
              Đây là đề xuất của AI ({result.model}), chưa được lưu. Hãy đọc giả định, chọn test phù hợp rồi lưu; test được lưu ở trạng thái
              Nháp để rà soát trước khi chạy.
            </div>
            <AIList title="Giả định chung" items={result.assumptions} />
            {result.drafts.length === 0 ? (
              <p className="text-sm text-muted-foreground">AI không đưa ra đề xuất nào.</p>
            ) : (
              <ul className="grid gap-2">
                {result.drafts.map((d, i) => (
                  <DraftCard key={i} draft={d} checked={picked.has(i)} onToggle={() => toggle(i)} />
                ))}
              </ul>
            )}
            <div className="flex flex-wrap gap-2">
              <Button disabled={picked.size === 0} loading={save.isPending} onClick={() => save.mutate()}>
                Lưu {picked.size} test case đã chọn
              </Button>
              <Button variant="outline" onClick={() => setResult(null)}>
                Bỏ đề xuất
              </Button>
              <Button variant="ghost" asChild>
                <Link to={`/test-cases?project=${project.id}`}>Xem test case</Link>
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function AIAssistantPage() {
  const { query: pq, projects, selected, select } = useProjectSelection();
  const status = useAIStatus();
  return (
    <>
      <PageHeader
        title="Trợ lý AI"
        description="Đề xuất test case từ mô tả yêu cầu. AI chỉ đề xuất; bạn duyệt mới được lưu. Phân tích lỗi có ở trang chi tiết lần chạy."
      />
      {(pq.isPending || status.isPending) && <LoadingState />}
      {pq.isError && <ErrorState message={pq.error.message} onRetry={() => pq.refetch()} />}
      {status.data && !status.data.configured && (
        <EmptyState
          icon={<Bot className="size-6" />}
          title="AI chưa được cấu hình"
          description="Quản trị hệ thống cần đặt OMNITEST_AI_PROVIDER và khóa API trên máy chủ. Mọi chức năng khác vẫn dùng bình thường."
        />
      )}
      {status.data?.configured && selected && (
        <div className="grid gap-4">
          <Card>
            <CardContent className="grid gap-3 p-4 sm:grid-cols-2 sm:p-5 lg:max-w-2xl">
              <ProjectPicker id="ai-project" projects={projects} value={selected.id} onChange={select} />
              <p className="self-end text-sm text-muted-foreground">Mô hình: {status.data.model}</p>
            </CardContent>
          </Card>
          {!selected.ai_enabled ? (
            <EmptyState
              title="Dự án chưa bật AI"
              description="Admin dự án bật “Cho phép dùng Trợ lý AI” trong trang chi tiết dự án nếu đồng ý gửi dữ liệu của dự án tới nhà cung cấp AI."
            />
          ) : !can(selected.my_role, "manager") || selected.is_archived ? (
            <EmptyState title="Bạn chưa có quyền tạo test case trong dự án này" description="Cần vai trò Manager trở lên." />
          ) : (
            <Suggest key={selected.id} project={selected} />
          )}
        </div>
      )}
    </>
  );
}
