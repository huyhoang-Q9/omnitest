import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, type OpenApiImportResult } from "@/lib/api";

/** Nội dung chỉ mount khi hộp thoại mở, nên mỗi lần mở là trạng thái mới. */
function OpenApiImportBody({ projectId, onDone }: { projectId: string; onDone: () => void }) {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [tag, setTag] = useState("");
  const [preview, setPreview] = useState<OpenApiImportResult | null>(null);
  const send = (dryRun: boolean) => {
    const body = new FormData();
    body.append("file", file as File);
    const qs = new URLSearchParams({ dry_run: String(dryRun) });
    if (tag.trim()) qs.set("tag", tag.trim());
    return api<OpenApiImportResult>(`/api/projects/${projectId}/test-cases/import-openapi?${qs}`, { method: "POST", body });
  };
  const check = useMutation({ mutationFn: () => send(true), onSuccess: setPreview, onError: (e) => toast.error(e.message) });
  const apply = useMutation({
    mutationFn: () => send(false),
    onSuccess: (r) => {
      toast.success(`Đã tạo ${r.created} test case nháp${r.skipped_duplicates ? `, bỏ qua ${r.skipped_duplicates} đã có` : ""}`);
      void qc.invalidateQueries({ queryKey: ["test-cases"] });
      onDone();
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <>
      <div className="grid gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="openapi-file">Tài liệu OpenAPI 3.x (.json, .yaml, tối đa 2 MB)</Label>
          <Input
            id="openapi-file"
            type="file"
            accept=".json,.yaml,.yml"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setPreview(null);
            }}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="openapi-tag">Nhãn thêm cho test case (không bắt buộc)</Label>
          <Input id="openapi-tag" maxLength={50} value={tag} onChange={(e) => setTag(e.target.value)} placeholder="VD: api-v1" />
        </div>
      </div>
      {preview && (
        <div className="grid min-w-0 gap-2 rounded-md border p-3 text-sm" role="status">
          <p>
            {preview.api_title || "API"} {preview.api_version && `(${preview.api_version})`}: {preview.operations} operation,{" "}
            {preview.created} sẽ tạo mới, {preview.skipped_duplicates} đã có (bỏ qua).
          </p>
          {preview.warnings.length > 0 && (
            <ul className="list-disc space-y-1 pl-5 text-status-blocked">
              {preview.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
          <ul className="max-h-56 space-y-1.5 overflow-y-auto">
            {preview.items.map((it) => (
              <li key={`${it.method} ${it.path}`} className="flex min-w-0 flex-wrap items-center gap-1.5">
                <Badge variant="outline">{it.method}</Badge>
                <span className="min-w-0 break-all font-mono text-xs">{it.path}</span>
                {it.side_effect && <Badge variant="muted">thay đổi dữ liệu</Badge>}
                {it.duplicate && <Badge variant="muted">đã có</Badge>}
                {it.variables.length > 0 && <span className="text-xs text-muted-foreground">cần biến: {it.variables.join(", ")}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <DialogFooter>
        <Button variant="outline" onClick={onDone}>
          Hủy
        </Button>
        {!preview ? (
          <Button disabled={!file} loading={check.isPending} onClick={() => check.mutate()}>
            Xem trước
          </Button>
        ) : (
          <Button disabled={preview.created === 0} loading={apply.isPending} onClick={() => apply.mutate()}>
            Tạo {preview.created} test case nháp
          </Button>
        )}
      </DialogFooter>
    </>
  );
}

export function OpenApiImportDialog({ projectId, open, onOpenChange }: { projectId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Tạo test case API từ OpenAPI</DialogTitle>
          <DialogDescription>
            Mỗi operation thành một test case trạng thái Nháp, kiểm tra mã trạng thái thành công. Giá trị không có ví dụ được thay bằng biến
            môi trường; hãy rà soát trước khi chuyển sang Sẵn sàng. Test luôn gọi Base URL của môi trường được chọn khi chạy.
          </DialogDescription>
        </DialogHeader>
        {open && <OpenApiImportBody projectId={projectId} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}
