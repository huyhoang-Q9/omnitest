import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, ApiError, type Run } from "@/lib/api";

export type RunRequest = {
  environment_id: string;
  test_case_ids: string[];
  suite_id: string | null;
  confirm: boolean;
};

/**
 * Tạo lần chạy và chuyển tới trang kết quả. Khi máy chủ trả 409 cần xác nhận, giữ lại lý do để giao diện
 * hiển thị; người dùng bấm lần nữa (confirm=true) mới chạy.
 */
export function useStartRun(projectId: string, onStarted?: () => void) {
  const navigate = useNavigate();
  const [reasons, setReasons] = useState<string[] | null>(null);
  const start = useMutation({
    mutationFn: (body: RunRequest) =>
      api<Run>(`/api/projects/${projectId}/runs`, { method: "POST", json: body }),
    onSuccess: (run) => {
      toast.success("Đã đưa lần chạy vào hàng đợi");
      onStarted?.();
      navigate(`/test-runs/${run.id}`);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409 && e.detail?.code === "confirmation_required") {
        setReasons(e.detail.reasons ?? []);
        return;
      }
      toast.error(e.message);
    },
  });
  return { start, reasons, clearReasons: () => setReasons(null) };
}
