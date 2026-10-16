import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Play } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useStartRun } from "@/hooks/start-run";
import { api, ENV_KIND_LABEL, type Environment } from "@/lib/api";

/**
 * Chạy test case hoặc suite trên một môi trường.
 * Máy chủ trả 409 kèm lý do khi cần xác nhận (môi trường UAT/Staging, test thay đổi dữ liệu);
 * người dùng phải đọc lý do và bấm xác nhận lần nữa thì mới tạo lần chạy.
 */
type RunDialogProps = {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  projectId: string;
  testCaseIds?: string[];
  suiteId?: string;
  label: string;
};

/** Lý do cần xác nhận do máy chủ trả về, hiển thị trước nút "Tôi xác nhận, chạy". */
export function ConfirmReasons({ reasons }: { reasons: string[] }) {
  return (
    <div role="alert" className="grid gap-2 rounded-md border border-status-blocked/40 bg-status-blocked/10 p-3 text-sm">
      <p className="flex items-center gap-2 font-medium">
        <AlertTriangle className="size-4 text-status-blocked" /> Cần xác nhận trước khi chạy
      </p>
      <ul className="list-disc space-y-1 pl-5">
        {reasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </div>
  );
}

/** Môi trường trỏ tới địa chỉ nội bộ mà Admin chưa cho phép mạng nội bộ: báo trước là test sẽ bị chặn. */
export function PrivateNetworkHint({ env }: { env: Environment }) {
  const isPrivate = /^(https?:\/\/)(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(env.base_url);
  if (env.allow_private_network || !isPrivate) return null;
  return (
    <p className="text-xs text-status-blocked">
      Môi trường trỏ tới địa chỉ nội bộ nhưng chưa được Admin cho phép mạng nội bộ: test sẽ bị chặn.
    </p>
  );
}

export function RunDialog(props: RunDialogProps) {
  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className="max-w-lg">
        {/* Nội dung chỉ được dựng khi mở, nên lý do xác nhận cũ không còn sót lại ở lần mở sau. */}
        <RunDialogBody {...props} />
      </DialogContent>
    </Dialog>
  );
}

function RunDialogBody({
  onOpenChange,
  projectId,
  testCaseIds,
  suiteId,
  label,
}: RunDialogProps) {
  const envs = useQuery({
    queryKey: ["environments", projectId],
    queryFn: () =>
      api<Environment[]>(`/api/projects/${projectId}/environments`),
  });
  const [chosenEnv, setEnvId] = useState("");
  const env = envs.data?.find((e) => e.id === chosenEnv) ?? envs.data?.[0];
  const envId = env?.id ?? "";

  const { start: m, reasons, clearReasons } = useStartRun(projectId, () => onOpenChange(false));

  return (
    <>
      <DialogHeader>
        <DialogTitle>Chạy test</DialogTitle>
        <DialogDescription>{label}</DialogDescription>
      </DialogHeader>
      {envs.isError && (
        <p className="text-sm text-status-failed">{envs.error.message}</p>
      )}
      {envs.data?.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Dự án chưa có môi trường. Hãy thêm môi trường trước khi chạy test.
        </p>
      )}
      {!!envs.data?.length && (
        <div className="grid gap-1.5">
          <Label htmlFor="run-env">Môi trường</Label>
          <NativeSelect
            id="run-env"
            value={envId}
            onChange={(e) => {
              setEnvId(e.target.value);
              clearReasons();
            }}
          >
            {envs.data.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name} ({ENV_KIND_LABEL[e.kind]}) · {e.base_url}
              </option>
            ))}
          </NativeSelect>
          {env && <PrivateNetworkHint env={env} />}
        </div>
      )}
      {reasons && <ConfirmReasons reasons={reasons} />}
      <DialogFooter>
        <Button
          type="button"
          variant="outline"
          onClick={() => onOpenChange(false)}
        >
          Hủy
        </Button>
        <Button
          type="button"
          variant={reasons ? "destructive" : "default"}
          disabled={!envId}
          loading={m.isPending}
          onClick={() =>
            m.mutate({
              environment_id: envId,
              test_case_ids: testCaseIds ?? [],
              suite_id: suiteId ?? null,
              confirm: !!reasons,
            })
          }
        >
          <Play /> {reasons ? "Tôi xác nhận, chạy" : "Chạy"}
        </Button>
      </DialogFooter>
    </>
  );
}
