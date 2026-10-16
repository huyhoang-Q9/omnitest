import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Globe, Layers, ListChecks, Play, Plus, Search, Zap } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfirmReasons, PrivateNetworkHint } from "@/features/run-dialog";
import { useStartRun } from "@/hooks/start-run";
import {
  api,
  can,
  ENV_KIND_LABEL,
  type Environment,
  type EnvironmentKind,
  type Page,
  type Project,
  type Suite,
  type TestCase,
} from "@/lib/api";
import { missingQuickCases, QUICK_CASES, QUICK_TAG, quickCaseBody } from "@/lib/quick-check";
import { TEST_TYPE_LABEL } from "@/lib/test-labels";
import { cn } from "@/lib/utils";

type Mode = "quick" | "suite" | "cases";

const capitalize = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

function Step({ n, title, done, children }: { n: number; title: string; done: boolean; children: ReactNode }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center gap-3 space-y-0">
        <span
          className={cn(
            "grid size-8 shrink-0 place-items-center rounded-full text-sm font-semibold",
            done ? "bg-status-passed text-white" : "bg-primary text-primary-foreground",
          )}
          aria-hidden
        >
          {done ? <Check className="size-4" /> : n}
        </span>
        <CardTitle className="text-lg">
          <span className="sr-only">Bước {n}: </span>
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
    </Card>
  );
}

function Choice({
  selected,
  onSelect,
  icon,
  title,
  description,
  name,
}: {
  selected: boolean;
  onSelect: () => void;
  icon: ReactNode;
  title: string;
  description: ReactNode;
  name: string;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer gap-3 rounded-lg border p-4 transition-colors hover:bg-muted/60",
        selected && "border-primary bg-accent/60 ring-1 ring-primary",
      )}
    >
      <input type="radio" name={name} className="sr-only" checked={selected} onChange={onSelect} />
      <span className="mt-0.5 text-primary">{icon}</span>
      <span className="min-w-0">
        <span className="block font-medium">{title}</span>
        <span className="block text-sm text-muted-foreground">{description}</span>
      </span>
    </label>
  );
}

/** Thêm hệ thống (môi trường) mới ngay trong luồng kiểm thử: chỉ tên, loại, URL. Cấu hình chi tiết ở trang Môi trường. */
function NewSystemForm({ projectId, onCreated }: { projectId: string; onCreated: (env: Environment) => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("https://");
  const [kind, setKind] = useState<EnvironmentKind>("test");
  const m = useMutation({
    mutationFn: () =>
      api<Environment>(`/api/projects/${projectId}/environments`, {
        method: "POST",
        json: { name, kind, base_url: url },
      }),
    onSuccess: (env) => {
      toast.success(`Đã thêm hệ thống ${env.name}`);
      void qc.invalidateQueries({ queryKey: ["environments"] });
      onCreated(env);
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <form
      className="grid gap-3 rounded-lg border border-dashed p-4 sm:grid-cols-[1fr_8rem_2fr_auto] sm:items-end"
      onSubmit={(e) => {
        e.preventDefault();
        m.mutate();
      }}
    >
      <div className="grid gap-1.5">
        <Label htmlFor="new-env-name">Tên hệ thống</Label>
        <Input id="new-env-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="VD: Cổng thông tin" required />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="new-env-kind">Loại</Label>
        <NativeSelect id="new-env-kind" value={kind} onChange={(e) => setKind(e.target.value as EnvironmentKind)}>
          {(Object.keys(ENV_KIND_LABEL) as EnvironmentKind[]).map((k) => (
            <option key={k} value={k}>
              {ENV_KIND_LABEL[k]}
            </option>
          ))}
        </NativeSelect>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="new-env-url">Địa chỉ (URL)</Label>
        <Input id="new-env-url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} required />
      </div>
      <Button type="submit" loading={m.isPending}>
        <Plus /> Thêm
      </Button>
    </form>
  );
}

function CasePicker({
  projectId,
  selected,
  onChange,
}: {
  projectId: string;
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const [q, setQ] = useState("");
  const cases = useQuery({
    queryKey: ["test-cases", projectId, { q, wizard: true }],
    queryFn: () =>
      api<Page<TestCase>>(
        `/api/projects/${projectId}/test-cases?page_size=50${q ? `&q=${encodeURIComponent(q)}` : ""}`,
      ),
  });
  const toggle = (id: string) => onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  return (
    <div className="space-y-2">
      <div className="relative">
        <Search className="absolute top-2.5 left-3 size-4 text-muted-foreground" aria-hidden />
        <Input aria-label="Tìm test case" className="pl-9" placeholder="Tìm theo mã hoặc tên" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {cases.isPending && <LoadingState rows={2} />}
      {cases.isError && <ErrorState message={cases.error.message} />}
      {cases.data?.items.length === 0 && <p className="py-3 text-sm text-muted-foreground">Không có test case phù hợp.</p>}
      <ul className="max-h-72 divide-y overflow-y-auto rounded-md border">
        {cases.data?.items.map((c) => (
          <li key={c.id}>
            <label className="flex cursor-pointer items-center gap-3 px-3 py-2 text-sm hover:bg-muted/60">
              <input type="checkbox" className="size-4 accent-[var(--primary)]" checked={selected.includes(c.id)} onChange={() => toggle(c.id)} />
              <span className="font-mono text-xs text-muted-foreground">{c.code}</span>
              <span className="min-w-0 flex-1 truncate">{c.title}</span>
              <span className="hidden text-xs text-muted-foreground sm:inline">{TEST_TYPE_LABEL[c.test_type]}</span>
            </label>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">Đã chọn {selected.length} test case.</p>
    </div>
  );
}

/**
 * Luồng kiểm thử theo 3 bước dành cho người kiểm thử: chọn hệ thống, chọn nội dung, xác nhận và chạy.
 * Mọi kết quả đến từ worker chạy thật; "Kiểm tra nhanh" chỉ là hai test case bình thường được tạo sẵn trong dự án.
 */
export function TestWizardPage() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    setParams(next, { replace: true });
  };

  const projects = useQuery({
    queryKey: ["projects", { all: true }],
    queryFn: () => api<Page<Project>>("/api/projects?page_size=100"),
  });
  const project = projects.data?.items.find((p) => p.id === params.get("project")) ?? projects.data?.items[0];
  const projectId = project?.id ?? "";
  const isManager = can(project?.my_role, "manager");
  const canRun = can(project?.my_role, "tester");

  const envs = useQuery({
    queryKey: ["environments", projectId],
    queryFn: () => api<Environment[]>(`/api/projects/${projectId}/environments`),
    enabled: !!projectId,
  });
  const env = envs.data?.find((e) => e.id === params.get("env")) ?? envs.data?.[0];
  const [addingSystem, setAddingSystem] = useState(false);

  const mode = (["quick", "suite", "cases"].includes(params.get("mode") ?? "") ? params.get("mode") : "quick") as Mode;
  const suites = useQuery({
    queryKey: ["suites", projectId],
    queryFn: () => api<Suite[]>(`/api/projects/${projectId}/suites`),
    enabled: !!projectId,
  });
  const suite = suites.data?.find((s) => s.id === params.get("suite")) ?? suites.data?.[0];
  const quick = useQuery({
    queryKey: ["test-cases", projectId, { tag: QUICK_TAG }],
    queryFn: () => api<Page<TestCase>>(`/api/projects/${projectId}/test-cases?tag=${QUICK_TAG}&page_size=50`),
    enabled: !!projectId,
  });
  const quickMissing = quick.data ? missingQuickCases(quick.data.items) : QUICK_CASES;
  const [caseIds, setCaseIds] = useState<string[]>([]);

  const prepareQuick = useMutation({
    mutationFn: async () => {
      for (const c of quickMissing)
        await api<TestCase>(`/api/projects/${projectId}/test-cases`, { method: "POST", json: quickCaseBody(c) });
    },
    onSuccess: () => {
      toast.success("Đã tạo bộ kiểm tra nhanh cho dự án");
      void qc.invalidateQueries({ queryKey: ["test-cases", projectId] });
    },
    onError: (e) => toast.error(e.message),
  });

  const { start, reasons, clearReasons } = useStartRun(projectId);

  if (projects.isPending) return <LoadingState rows={4} />;
  if (projects.isError) return <ErrorState message={projects.error.message} onRetry={() => projects.refetch()} />;
  if (!project)
    return (
      <EmptyState
        title="Bạn chưa thuộc dự án nào"
        description="Kiểm thử luôn gắn với một dự án. Hãy nhờ quản trị hệ thống tạo dự án hoặc thêm bạn vào dự án."
      />
    );

  const quickIds = (quick.data?.items ?? []).filter((t) => QUICK_CASES.some((c) => c.title === t.title)).map((t) => t.id);
  const scope =
    mode === "quick"
      ? { test_case_ids: quickIds, suite_id: null, ready: quickMissing.length === 0 && quickIds.length > 0, label: "Kiểm tra nhanh (2 test)" }
      : mode === "suite"
        ? { test_case_ids: [], suite_id: suite?.id ?? null, ready: !!suite && suite.case_count > 0, label: suite ? `Bộ test "${suite.name}" (${suite.case_count} test)` : "" }
        : { test_case_ids: caseIds, suite_id: null, ready: caseIds.length > 0, label: `${caseIds.length} test case đã chọn` };

  const step1Done = !!env;
  const step2Done = scope.ready;

  return (
    <>
      <PageHeader
        title="Kiểm thử hệ thống"
        description="Ba bước: chọn hệ thống, chọn nội dung kiểm thử, rồi chạy và theo dõi kết quả trực tiếp."
      />
      <div className="mx-auto grid max-w-4xl gap-5">
        <Step n={1} title="Chọn hệ thống cần kiểm thử" done={step1Done}>
          <div className="grid gap-1.5 sm:max-w-sm">
            <Label htmlFor="wizard-project">Dự án</Label>
            <NativeSelect
              id="wizard-project"
              value={projectId}
              onChange={(e) => {
                clearReasons();
                setCaseIds([]);
                set({ project: e.target.value, env: null, suite: null });
              }}
            >
              {projects.data.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.key} · {p.name}
                </option>
              ))}
            </NativeSelect>
          </div>
          {envs.isPending && <LoadingState rows={2} />}
          {envs.isError && <ErrorState message={envs.error.message} />}
          {envs.data && (
            <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Hệ thống">
              {envs.data.map((e) => (
                <Choice
                  key={e.id}
                  name="wizard-env"
                  selected={env?.id === e.id}
                  onSelect={() => {
                    clearReasons();
                    set({ env: e.id });
                  }}
                  icon={<Globe className="size-5" />}
                  title={`${e.name} · ${ENV_KIND_LABEL[e.kind]}`}
                  description={<span className="break-all">{e.base_url}</span>}
                />
              ))}
            </div>
          )}
          {envs.data?.length === 0 && !isManager && (
            <p className="text-sm text-muted-foreground">Dự án chưa có hệ thống nào. Manager của dự án cần thêm trước.</p>
          )}
          {isManager &&
            (addingSystem || envs.data?.length === 0 ? (
              <NewSystemForm
                projectId={projectId}
                onCreated={(e) => {
                  setAddingSystem(false);
                  set({ env: e.id });
                }}
              />
            ) : (
              <Button variant="outline" size="sm" onClick={() => setAddingSystem(true)}>
                <Plus /> Thêm hệ thống khác
              </Button>
            ))}
          {env && <PrivateNetworkHint env={env} />}
        </Step>

        <Step n={2} title="Chọn nội dung kiểm thử" done={step2Done}>
          <div className="grid gap-3 md:grid-cols-3" role="radiogroup" aria-label="Nội dung kiểm thử">
            <Choice
              name="wizard-mode"
              selected={mode === "quick"}
              onSelect={() => set({ mode: "quick" })}
              icon={<Zap className="size-5" />}
              title="Kiểm tra nhanh"
              description="Hệ thống có phản hồi không, trang web có mở được không (kèm ảnh chụp)."
            />
            <Choice
              name="wizard-mode"
              selected={mode === "suite"}
              onSelect={() => set({ mode: "suite" })}
              icon={<Layers className="size-5" />}
              title="Chạy bộ test"
              description="Chạy một bộ test (suite) đã soạn sẵn cho dự án."
            />
            <Choice
              name="wizard-mode"
              selected={mode === "cases"}
              onSelect={() => set({ mode: "cases" })}
              icon={<ListChecks className="size-5" />}
              title="Chọn test case"
              description="Tự chọn từng test case cần chạy."
            />
          </div>

          {mode === "quick" &&
            (quick.isPending ? (
              <LoadingState rows={1} />
            ) : quickMissing.length > 0 ? (
              <div className="grid gap-2 rounded-lg bg-muted/60 p-4 text-sm">
                <p>
                  Dự án chưa có bộ kiểm tra nhanh. Portal sẽ tạo {quickMissing.length} test case thường (gắn tag{" "}
                  <code className="rounded bg-card px-1">{QUICK_TAG}</code>), xem và sửa được ở trang Test case.
                </p>
                {isManager ? (
                  <Button className="justify-self-start" size="sm" onClick={() => prepareQuick.mutate()} loading={prepareQuick.isPending}>
                    <Plus /> Tạo bộ kiểm tra nhanh
                  </Button>
                ) : (
                  <p className="text-muted-foreground">Cần quyền Manager để tạo. Hãy nhờ Manager của dự án.</p>
                )}
              </div>
            ) : (
              <ul className="grid gap-1 text-sm">
                {QUICK_CASES.map((c) => (
                  <li key={c.title} className="flex gap-2">
                    <Check className="mt-0.5 size-4 shrink-0 text-status-passed" aria-hidden />
                    <span>
                      <span className="font-medium">{capitalize(c.title.replace("Kiểm tra nhanh: ", ""))}</span>
                      <span className="text-muted-foreground"> · {c.expected_result}</span>
                    </span>
                  </li>
                ))}
              </ul>
            ))}

          {mode === "suite" &&
            (suites.data?.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Dự án chưa có bộ test. <Link className="text-primary hover:underline" to="/test-suites">Tạo bộ test</Link>
              </p>
            ) : (
              <div className="grid gap-1.5 sm:max-w-md">
                <Label htmlFor="wizard-suite">Bộ test</Label>
                <NativeSelect id="wizard-suite" value={suite?.id} onChange={(e) => set({ suite: e.target.value })}>
                  {suites.data?.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.case_count} test)
                    </option>
                  ))}
                </NativeSelect>
                {suite && suite.case_count === 0 && <p className="text-xs text-status-blocked">Bộ test này chưa có test case.</p>}
              </div>
            ))}

          {mode === "cases" && <CasePicker projectId={projectId} selected={caseIds} onChange={setCaseIds} />}
        </Step>

        <Step n={3} title="Chạy và xem kết quả" done={false}>
          <dl className="grid gap-2 text-sm sm:grid-cols-[8rem_1fr]">
            <dt className="text-muted-foreground">Dự án</dt>
            <dd>{project.name}</dd>
            <dt className="text-muted-foreground">Hệ thống</dt>
            <dd className="break-all">{env ? `${env.name} · ${env.base_url}` : "Chưa chọn"}</dd>
            <dt className="text-muted-foreground">Nội dung</dt>
            <dd>{scope.ready ? scope.label : "Chưa đủ"}</dd>
          </dl>
          {reasons && <ConfirmReasons reasons={reasons} />}
          {!canRun && <p className="text-sm text-muted-foreground">Bạn đang có quyền Viewer: chỉ xem được kết quả, không chạy được test.</p>}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              size="lg"
              variant={reasons ? "destructive" : "default"}
              disabled={!env || !scope.ready || !canRun}
              loading={start.isPending}
              onClick={() =>
                env &&
                start.mutate({
                  environment_id: env.id,
                  test_case_ids: scope.test_case_ids,
                  suite_id: scope.suite_id,
                  confirm: !!reasons,
                })
              }
            >
              <Play /> {reasons ? "Tôi xác nhận, chạy" : "Bắt đầu kiểm thử"}
            </Button>
            <p className="text-xs text-muted-foreground">Kết quả từng bước, ảnh chụp và log cập nhật trực tiếp sau khi bấm.</p>
          </div>
        </Step>
      </div>
    </>
  );
}
