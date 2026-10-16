/** Script code (pytest/Playwright) chạy trong sandbox Docker: công tắc dự án và trình soạn file. */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useSandboxStatus } from "@/hooks/sandbox";
import { api, type Project } from "@/lib/api";
import type { Definition } from "@/lib/definition";

/** Công tắc cho phép script code trong dự án (chỉ Admin dự án). */
export function ProjectScriptToggle({ project, canEdit }: { project: Project; canEdit: boolean }) {
  const qc = useQueryClient();
  const sandbox = useSandboxStatus();
  const m = useMutation({
    mutationFn: (enabled: boolean) => api<Project>(`/api/projects/${project.id}`, { method: "PATCH", json: { script_enabled: enabled } }),
    onSuccess: (p) => {
      qc.setQueryData(["project", p.id], p);
      void qc.invalidateQueries({ queryKey: ["projects"] });
      toast.success(p.script_enabled ? "Đã cho phép script code trong dự án" : "Đã tắt script code trong dự án");
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <div className="mb-5 flex items-start gap-3 rounded-lg border px-4 py-3 text-sm">
      <Switch
        id="project-script"
        checked={project.script_enabled}
        disabled={!canEdit || project.is_archived || m.isPending}
        onCheckedChange={(v) => m.mutate(v)}
        aria-describedby="project-script-help"
      />
      <div className="min-w-0 space-y-0.5">
        <Label htmlFor="project-script">Cho phép test script code (pytest/Playwright)</Label>
        <p id="project-script-help" className="text-muted-foreground">
          Script do Admin dự án viết, chạy trong container Docker cô lập (không mạng mặc định, không root, giới hạn CPU, RAM, thời
          gian). Chỉ Admin dự án tạo và sửa được script; mỗi lần chạy cần xác nhận.
          {!canEdit && " Chỉ Admin dự án được thay đổi."}
          {sandbox.data && !sandbox.data.environment_ok && " Máy chủ hiện chưa bật sandbox nên script sẽ báo Bị chặn khi chạy."}
        </p>
      </div>
    </div>
  );
}


const NAME_RE = /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}\.(py|json|csv|txt|yaml|yml)$/;

export function ScriptEditor({ value, onChange }: { value: Definition; onChange: (d: Definition) => void }) {
  const sandbox = useSandboxStatus();
  const files = (value.files as Record<string, string> | undefined) ?? {};
  // Giữ thứ tự và tên đang gõ dở (tên trùng hoặc rỗng không được ghi đè lên file khác).
  const [rows, setRows] = useState<[string, string][]>(() => Object.entries(files));
  const commit = (next: [string, string][]) => {
    setRows(next);
    onChange({ ...value, files: Object.fromEntries(next) });
  };
  return (
    <div className="grid gap-4">
      <div role="note" className="rounded-md border border-status-blocked/40 bg-status-blocked/10 p-3 text-sm">
        Script <strong>pytest</strong> chạy trong <strong>container Docker cô lập</strong>: người dùng không root, không có quyền hệ
        thống, giới hạn CPU, RAM, số tiến trình và thời gian; mặc định <strong>không có mạng</strong>. Biến môi trường có dạng{" "}
        <code>OMNITEST_VAR_TEN_BIEN</code>, Base URL ở <code>OMNITEST_BASE_URL</code>, file lưu vào <code>OMNITEST_ARTIFACTS_DIR</code> được
        giữ làm bằng chứng. Secret được che trong log, nhưng script vẫn đọc được giá trị thật.
        {sandbox.data && !sandbox.data.environment_ok && (
          <>
            {" "}
            <strong>Máy chủ chưa bật sandbox, chạy sẽ báo Bị chặn.</strong>
          </>
        )}
      </div>
      <div className="grid gap-1.5 sm:max-w-md">
        <Label htmlFor="script-network">Mạng</Label>
        <NativeSelect id="script-network" value={String(value.network ?? "none")} onChange={(e) => onChange({ ...value, network: e.target.value })}>
          <option value="none">Không có mạng (an toàn nhất)</option>
          <option value="environment">Qua proxy của môi trường (chỉ host được phép)</option>
        </NativeSelect>
        <p className="text-xs text-muted-foreground">
          Chế độ proxy áp dụng đúng chính sách mạng của môi trường: chỉ host trong danh sách, mạng nội bộ cần Admin bật, luôn chặn
          metadata cloud.
        </p>
      </div>
      <ol className="grid gap-3" aria-label="Các file">
        {rows.map(([name, content], i) => {
          const dup = rows.some(([n], j) => j !== i && n === name);
          const bad = !NAME_RE.test(name);
          return (
            <li key={i} className="grid min-w-0 gap-2 rounded-lg border p-3">
              <div className="flex items-end gap-2">
                <div className="grid min-w-0 flex-1 gap-1.5">
                  <Label htmlFor={`script-name-${i}`}>Tên file</Label>
                  <Input
                    id={`script-name-${i}`}
                    className="font-mono"
                    value={name}
                    aria-invalid={dup || bad}
                    onChange={(e) => commit(rows.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))}
                  />
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Xóa file ${name}`}
                  disabled={rows.length === 1}
                  onClick={() => commit(rows.filter((_, j) => j !== i))}
                >
                  <Trash2 />
                </Button>
              </div>
              {(dup || bad) && (
                <p role="alert" className="text-xs text-status-failed">
                  {dup ? "Tên file bị trùng" : "Tên chỉ gồm chữ, số, _ . -, đuôi .py .json .csv .txt .yaml .yml"}
                </p>
              )}
              <Label htmlFor={`script-code-${i}`} className="sr-only">
                Nội dung {name}
              </Label>
              <Textarea
                id={`script-code-${i}`}
                rows={14}
                spellCheck={false}
                className="font-mono text-xs"
                value={content}
                onChange={(e) => commit(rows.map((r, j) => (j === i ? [r[0], e.target.value] : r)))}
              />
            </li>
          );
        })}
      </ol>
      <Button
        type="button"
        variant="outline"
        className="w-fit"
        disabled={rows.length >= 20}
        onClick={() => commit([...rows, [`test_file_${rows.length + 1}.py`, "def test_vi_du():\n    assert True\n"]])}
      >
        <Plus /> Thêm file
      </Button>
      <p className="text-xs text-muted-foreground">
        Cần ít nhất một file test_*.py. Tối đa 20 file, 256 KB. Có sẵn pytest, httpx, Playwright (Chromium, Firefox, WebKit).
      </p>
    </div>
  );
}
