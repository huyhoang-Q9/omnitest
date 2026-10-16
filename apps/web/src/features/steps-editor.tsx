/**
 * Trình soạn định nghĩa test dạng có cấu trúc (không cần viết code).
 * Định nghĩa được máy chủ kiểm tra lại đầy đủ khi lưu; ở đây chỉ chặn lỗi JSON để không mất dữ liệu đang gõ.
 */
import { ArrowDown, ArrowUp, Copy, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  ASSERTION_LABEL,
  COMPARATOR_LABEL,
  WEB_ACTION_LABEL,
  WEB_NEEDS_SELECTOR,
  WEB_NEEDS_VALUE,
} from "@/lib/test-labels";

import { formatLoose, INVALID, parseLoose, type Definition, type Obj } from "@/lib/definition";

function moveItem<T>(list: T[], i: number, d: number): T[] {
  const j = i + d;
  if (j < 0 || j >= list.length) return list;
  const next = [...list];
  [next[i], next[j]] = [next[j], next[i]];
  return next;
}

function JsonField({
  id,
  label,
  value,
  onChange,
  rows = 4,
  placeholder,
}: {
  id: string;
  label: string;
  value: unknown;
  onChange: (v: unknown) => void;
  rows?: number;
  placeholder?: string;
}) {
  const invalid = value && typeof value === "object" && INVALID in (value as Obj);
  const initial = invalid
    ? String((value as Obj)[INVALID])
    : value === null || value === undefined
      ? ""
      : JSON.stringify(value, null, 2);
  const [text, setText] = useState(initial);
  const [error, setError] = useState<string | null>(invalid ? "JSON không hợp lệ" : null);
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Textarea
        id={id}
        rows={rows}
        className="font-mono text-xs"
        value={text}
        placeholder={placeholder}
        aria-invalid={!!error}
        onChange={(e) => {
          const t = e.target.value;
          setText(t);
          if (t.trim() === "") {
            setError(null);
            onChange(null);
            return;
          }
          try {
            onChange(JSON.parse(t));
            setError(null);
          } catch {
            setError("JSON không hợp lệ");
            onChange({ [INVALID]: t });
          }
        }}
      />
      {error && (
        <p role="alert" className="text-xs text-status-failed">
          {error}
        </p>
      )}
    </div>
  );
}

function KeyValueEditor({
  idPrefix,
  label,
  value,
  onChange,
  keyPlaceholder,
}: {
  idPrefix: string;
  label: string;
  value: Record<string, string> | undefined;
  onChange: (v: Record<string, string>) => void;
  keyPlaceholder: string;
}) {
  const [rows, setRows] = useState<[string, string][]>(() => Object.entries(value ?? {}));
  const commit = (next: [string, string][]) => {
    setRows(next);
    onChange(Object.fromEntries(next.filter(([k]) => k.trim() !== "")));
  };
  return (
    <fieldset className="grid gap-2">
      <legend className="mb-1 text-sm font-medium">{label}</legend>
      {rows.map(([k, v], i) => (
        <div key={i} className="flex gap-2">
          <Input
            aria-label={`${label} ${i + 1} tên`}
            id={`${idPrefix}-k${i}`}
            placeholder={keyPlaceholder}
            value={k}
            onChange={(e) => commit(rows.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))}
          />
          <Input
            aria-label={`${label} ${i + 1} giá trị`}
            placeholder="Giá trị, có thể dùng {{BIEN}}"
            value={v}
            onChange={(e) => commit(rows.map((r, j) => (j === i ? [r[0], e.target.value] : r)))}
          />
          <Button type="button" variant="ghost" size="icon" aria-label="Xóa dòng" onClick={() => commit(rows.filter((_, j) => j !== i))}>
            <Trash2 />
          </Button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" className="w-fit" onClick={() => setRows([...rows, ["", ""]])}>
        <Plus /> Thêm
      </Button>
    </fieldset>
  );
}

function StepShell({
  index,
  total,
  title,
  onMove,
  onDuplicate,
  onRemove,
  children,
}: {
  index: number;
  total: number;
  title: string;
  onMove: (d: number) => void;
  onDuplicate: () => void;
  onRemove: () => void;
  children: React.ReactNode;
}) {
  return (
    <li className="min-w-0 rounded-lg border bg-card">
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <span className="grid size-6 shrink-0 place-items-center rounded-full bg-muted text-xs font-semibold">{index + 1}</span>
        <p className="min-w-0 flex-1 truncate text-sm font-medium">{title || "Bước chưa đặt tên"}</p>
        <Button type="button" variant="ghost" size="icon" aria-label={`Đưa bước ${index + 1} lên`} disabled={index === 0} onClick={() => onMove(-1)}>
          <ArrowUp />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={`Đưa bước ${index + 1} xuống`}
          disabled={index === total - 1}
          onClick={() => onMove(1)}
        >
          <ArrowDown />
        </Button>
        <Button type="button" variant="ghost" size="icon" aria-label={`Nhân bản bước ${index + 1}`} onClick={onDuplicate}>
          <Copy />
        </Button>
        <Button type="button" variant="ghost" size="icon" aria-label={`Xóa bước ${index + 1}`} disabled={total === 1} onClick={onRemove}>
          <Trash2 />
        </Button>
      </div>
      <div className="grid grid-cols-1 gap-4 p-3 sm:p-4">{children}</div>
    </li>
  );
}

// ---------- API ----------

const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"];

function AssertionRow({ a, onChange, onRemove, id }: { a: Obj; onChange: (a: Obj) => void; onRemove: () => void; id: string }) {
  const type = String(a.type);
  const setType = (t: string) => {
    const base: Record<string, Obj> = {
      status: { type: "status", equals: 200 },
      json_path: { type: "json_path", path: "$.", op: "equals", value: null },
      json_schema: { type: "json_schema", schema: { type: "object" } },
      header: { type: "header", name: "content-type", op: "contains", value: "json" },
      response_time: { type: "response_time", max_ms: 2000 },
    };
    onChange(base[t]);
  };
  return (
    <div className="grid gap-2 rounded-md border border-dashed p-2 sm:grid-cols-[180px_1fr_auto] sm:items-start">
      <NativeSelect aria-label="Loại kiểm tra" value={type} onChange={(e) => setType(e.target.value)}>
        {Object.entries(ASSERTION_LABEL).map(([k, v]) => (
          <option key={k} value={k}>
            {v}
          </option>
        ))}
      </NativeSelect>
      <div className="grid gap-2 sm:grid-cols-3">
        {type === "status" && (
          <Input
            aria-label="Mã trạng thái mong đợi"
            type="number"
            value={a.equals === undefined || a.equals === null ? "" : String(a.equals)}
            onChange={(e) => onChange({ type: "status", equals: e.target.value === "" ? null : Number(e.target.value) })}
          />
        )}
        {(type === "json_path" || type === "header") && (
          <>
            <Input
              aria-label={type === "header" ? "Tên header" : "Biểu thức JSONPath"}
              placeholder={type === "header" ? "content-type" : "$.data.id"}
              value={String(type === "header" ? (a.name ?? "") : (a.path ?? ""))}
              onChange={(e) => onChange({ ...a, [type === "header" ? "name" : "path"]: e.target.value })}
            />
            <NativeSelect aria-label="Phép so sánh" value={String(a.op ?? "equals")} onChange={(e) => onChange({ ...a, op: e.target.value })}>
              {Object.entries(COMPARATOR_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </NativeSelect>
            {!["exists", "not_exists"].includes(String(a.op)) && (
              <Input
                aria-label="Giá trị mong đợi"
                placeholder="Số, true/false hoặc chuỗi"
                value={formatLoose(a.value)}
                onChange={(e) => onChange({ ...a, value: type === "header" ? e.target.value : parseLoose(e.target.value) })}
              />
            )}
          </>
        )}
        {type === "response_time" && (
          <Input
            aria-label="Thời gian tối đa (ms)"
            type="number"
            value={String(a.max_ms ?? "")}
            onChange={(e) => onChange({ ...a, max_ms: Number(e.target.value) })}
          />
        )}
        {type === "json_schema" && (
          <div className="sm:col-span-3">
            <JsonField id={`${id}-schema`} label="JSON Schema" value={a.schema} onChange={(v) => onChange({ ...a, schema: v })} />
          </div>
        )}
      </div>
      <Button type="button" variant="ghost" size="icon" aria-label="Xóa kiểm tra" onClick={onRemove}>
        <Trash2 />
      </Button>
    </div>
  );
}

function ApiStepFields({ step, onChange, id }: { step: Obj; onChange: (s: Obj) => void; id: string }) {
  const auth = (step.auth as Obj | undefined) ?? { type: "none" };
  const assertions = (step.assertions as Obj[] | undefined) ?? [];
  const extract = (step.extract as Obj[] | undefined) ?? [];
  const bodyType = String(step.body_type ?? "none");
  const [aRev, setARev] = useState(0);
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-[1fr_120px_2fr]">
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-name`}>Tên bước</Label>
          <Input id={`${id}-name`} value={String(step.name ?? "")} onChange={(e) => onChange({ ...step, name: e.target.value })} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-method`}>Phương thức</Label>
          <NativeSelect id={`${id}-method`} value={String(step.method ?? "GET")} onChange={(e) => onChange({ ...step, method: e.target.value })}>
            {METHODS.map((m) => (
              <option key={m}>{m}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-url`}>URL</Label>
          <Input
            id={`${id}-url`}
            placeholder="/api/items hoặc URL đầy đủ trong host được phép"
            value={String(step.url ?? "")}
            onChange={(e) => onChange({ ...step, url: e.target.value })}
          />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-auth`}>Xác thực</Label>
          <NativeSelect
            id={`${id}-auth`}
            value={String(auth.type)}
            onChange={(e) => {
              const t = e.target.value;
              const next: Record<string, Obj> = {
                none: { type: "none" },
                basic: { type: "basic", username: "", password: "" },
                bearer: { type: "bearer", token: "" },
                api_key: { type: "api_key", header: "X-API-Key", value: "" },
              };
              onChange({ ...step, auth: next[t] });
            }}
          >
            <option value="none">Không</option>
            <option value="basic">Basic</option>
            <option value="bearer">Bearer token</option>
            <option value="api_key">API key</option>
          </NativeSelect>
        </div>
        {auth.type === "basic" && (
          <>
            <Input aria-label="Tên đăng nhập" placeholder="{{API_USER}}" className="self-end" value={String(auth.username ?? "")} onChange={(e) => onChange({ ...step, auth: { ...auth, username: e.target.value } })} />
            <Input aria-label="Mật khẩu" placeholder="{{API_PASSWORD}}" className="self-end" value={String(auth.password ?? "")} onChange={(e) => onChange({ ...step, auth: { ...auth, password: e.target.value } })} />
          </>
        )}
        {auth.type === "bearer" && (
          <Input aria-label="Token" placeholder="{{TOKEN}}" className="self-end sm:col-span-2" value={String(auth.token ?? "")} onChange={(e) => onChange({ ...step, auth: { ...auth, token: e.target.value } })} />
        )}
        {auth.type === "api_key" && (
          <>
            <Input aria-label="Tên header API key" className="self-end" value={String(auth.header ?? "")} onChange={(e) => onChange({ ...step, auth: { ...auth, header: e.target.value } })} />
            <Input aria-label="Giá trị API key" placeholder="{{API_KEY}}" className="self-end" value={String(auth.value ?? "")} onChange={(e) => onChange({ ...step, auth: { ...auth, value: e.target.value } })} />
          </>
        )}
      </div>
      {auth.type !== "none" && (
        <p className="-mt-2 text-xs text-muted-foreground">Nên dùng biến secret của môi trường, VD {"{{API_PASSWORD}}"}, thay vì nhập giá trị thật.</p>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <KeyValueEditor idPrefix={`${id}-h`} label="Header" keyPlaceholder="Tên header" value={step.headers as Record<string, string>} onChange={(v) => onChange({ ...step, headers: v })} />
        <KeyValueEditor idPrefix={`${id}-q`} label="Tham số query" keyPlaceholder="Tên tham số" value={step.query as Record<string, string>} onChange={(v) => onChange({ ...step, query: v })} />
      </div>

      <div className="grid gap-3 sm:grid-cols-[180px_1fr]">
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-bt`}>Body</Label>
          <NativeSelect id={`${id}-bt`} value={bodyType} onChange={(e) => onChange({ ...step, body_type: e.target.value, body: e.target.value === "none" ? null : step.body })}>
            <option value="none">Không có</option>
            <option value="json">JSON</option>
            <option value="text">Văn bản</option>
            <option value="form">Form (JSON object)</option>
          </NativeSelect>
        </div>
        {bodyType === "text" && (
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-body`}>Nội dung</Label>
            <Textarea id={`${id}-body`} rows={4} value={formatLoose(step.body)} onChange={(e) => onChange({ ...step, body: e.target.value })} />
          </div>
        )}
        {(bodyType === "json" || bodyType === "form") && (
          <JsonField
            id={`${id}-body`}
            label="Nội dung JSON"
            value={step.body}
            placeholder='{"username": "{{USER}}"}'
            onChange={(v) => onChange({ ...step, body: v })}
          />
        )}
      </div>

      <fieldset className="grid gap-2">
        <legend className="mb-1 text-sm font-medium">Kiểm tra kết quả</legend>
        {assertions.length === 0 && <p className="text-xs text-status-blocked">Chưa có kiểm tra nào: bước chỉ đạt khi gọi được máy chủ.</p>}
        {assertions.map((a, i) => (
          <AssertionRow
            key={`${aRev}-${i}`}
            id={`${id}-a${i}`}
            a={a}
            onChange={(na) => onChange({ ...step, assertions: assertions.map((x, j) => (j === i ? na : x)) })}
            onRemove={() => {
              setARev((r) => r + 1);
              onChange({ ...step, assertions: assertions.filter((_, j) => j !== i) });
            }}
          />
        ))}
        <Button type="button" variant="outline" size="sm" className="w-fit" onClick={() => onChange({ ...step, assertions: [...assertions, { type: "status", equals: 200 }] })}>
          <Plus /> Thêm kiểm tra
        </Button>
      </fieldset>

      <fieldset className="grid gap-2">
        <legend className="mb-1 text-sm font-medium">Lấy giá trị cho bước sau</legend>
        {extract.map((x, i) => (
          <div key={i} className="grid gap-2 sm:grid-cols-[1fr_140px_2fr_auto]">
            <Input aria-label="Tên biến" placeholder="TOKEN" value={String(x.var ?? "")} onChange={(e) => onChange({ ...step, extract: extract.map((y, j) => (j === i ? { ...y, var: e.target.value } : y)) })} />
            <NativeSelect aria-label="Nguồn" value={String(x.source ?? "json_path")} onChange={(e) => onChange({ ...step, extract: extract.map((y, j) => (j === i ? { ...y, source: e.target.value } : y)) })}>
              <option value="json_path">JSONPath</option>
              <option value="header">Header</option>
            </NativeSelect>
            <Input aria-label="Biểu thức" placeholder="$.token" value={String(x.expression ?? "")} onChange={(e) => onChange({ ...step, extract: extract.map((y, j) => (j === i ? { ...y, expression: e.target.value } : y)) })} />
            <Button type="button" variant="ghost" size="icon" aria-label="Xóa biến trích xuất" onClick={() => onChange({ ...step, extract: extract.filter((_, j) => j !== i) })}>
              <Trash2 />
            </Button>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" className="w-fit" onClick={() => onChange({ ...step, extract: [...extract, { var: "", source: "json_path", expression: "$." }] })}>
          <Plus /> Thêm biến
        </Button>
      </fieldset>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-to`}>Chờ phản hồi tối đa (ms)</Label>
          <Input id={`${id}-to`} type="number" min={100} max={300000} value={String(step.timeout_ms ?? 30000)} onChange={(e) => onChange({ ...step, timeout_ms: Number(e.target.value) })} />
        </div>
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <Switch checked={step.follow_redirects !== false} onCheckedChange={(v) => onChange({ ...step, follow_redirects: v })} aria-label="Theo chuyển hướng" />
          Theo chuyển hướng (kiểm tra từng đích)
        </label>
      </div>
    </>
  );
}

// ---------- Web ----------

function WebStepFields({ step, onChange, id }: { step: Obj; onChange: (s: Obj) => void; id: string }) {
  const action = String(step.action ?? "goto");
  const needsSelector = WEB_NEEDS_SELECTOR.has(action);
  const needsValue = WEB_NEEDS_VALUE.has(action);
  return (
    <div className="grid gap-3 lg:grid-cols-[1fr_200px_1.5fr_1.5fr_110px]">
      <div className="grid gap-1.5">
        <Label htmlFor={`${id}-name`}>Tên bước</Label>
        <Input id={`${id}-name`} value={String(step.name ?? "")} onChange={(e) => onChange({ ...step, name: e.target.value })} />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${id}-action`}>Hành động</Label>
        <NativeSelect id={`${id}-action`} value={action} onChange={(e) => onChange({ ...step, action: e.target.value })}>
          {Object.entries(WEB_ACTION_LABEL).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </NativeSelect>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${id}-sel`}>Phần tử{needsSelector && <span className="text-status-failed"> *</span>}</Label>
        <Input
          id={`${id}-sel`}
          placeholder={'label=Email, role=button[name="Lưu"], #id'}
          disabled={!needsSelector && action !== "screenshot"}
          value={String(step.selector ?? "")}
          onChange={(e) => onChange({ ...step, selector: e.target.value || null })}
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${id}-val`}>Giá trị{needsValue && <span className="text-status-failed"> *</span>}</Label>
        <Input
          id={`${id}-val`}
          placeholder={action === "goto" ? "/login" : action === "press" ? "Enter" : "Có thể dùng {{BIEN}}"}
          disabled={!needsValue}
          value={String(step.value ?? "")}
          onChange={(e) => onChange({ ...step, value: e.target.value || null })}
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${id}-to`}>Chờ (ms)</Label>
        <Input id={`${id}-to`} type="number" min={100} max={120000} value={String(step.timeout_ms ?? 10000)} onChange={(e) => onChange({ ...step, timeout_ms: Number(e.target.value) })} />
      </div>
    </div>
  );
}

// ---------- Tổng ----------

export function DefinitionEditor({ value, onChange }: { value: Definition; onChange: (d: Definition) => void }) {
  const [jsonMode, setJsonMode] = useState(false);
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);
  // Ô nhập con giữ trạng thái riêng; đổi rev khi thứ tự bước thay đổi để dựng lại đúng nội dung.
  const [rev, setRev] = useState(0);
  const kind = value.kind;
  const steps = (value.steps as Obj[] | undefined) ?? [];
  const setSteps = (s: Obj[]) => onChange({ ...value, steps: s });
  const restructure = (s: Obj[]) => {
    setRev((r) => r + 1);
    setSteps(s);
  };

  if (kind !== "api" && kind !== "web") {
    return (
      <div className="grid gap-3">
        <div role="note" className="rounded-md border border-status-blocked/40 bg-status-blocked/10 p-3 text-sm">
          Loại test này chưa có adapter chạy thật (cần driver và máy thật ở giai đoạn sau). Bạn có thể lưu mô tả các bước thủ công;
          khi chạy, kết quả sẽ là <strong>Bị chặn</strong>, không bao giờ báo đạt giả.
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="def-notes">Mô tả các bước</Label>
          <Textarea id="def-notes" rows={8} value={String(value.notes ?? "")} onChange={(e) => onChange({ ...value, notes: e.target.value })} />
        </div>
      </div>
    );
  }

  const toggleJson = () => {
    if (!jsonMode) {
      setJsonText(JSON.stringify(value, null, 2));
      setJsonError(null);
      setJsonMode(true);
      return;
    }
    try {
      const parsed = JSON.parse(jsonText) as Definition;
      if (parsed.kind !== kind) throw new Error(`kind phải là "${kind}"`);
      onChange(parsed);
      setRev((r) => r + 1);
      setJsonMode(false);
    } catch (e) {
      setJsonError(`Không áp dụng được JSON: ${(e as Error).message}`);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        {kind === "web" && !jsonMode ? (
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="grid gap-1.5">
              <Label htmlFor="def-browser">Trình duyệt</Label>
              <NativeSelect id="def-browser" value={String(value.browser ?? "chromium")} onChange={(e) => onChange({ ...value, browser: e.target.value })}>
                <option value="chromium">Chromium</option>
                <option value="firefox">Firefox</option>
                <option value="webkit">WebKit</option>
              </NativeSelect>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="def-vw">Rộng (px)</Label>
              <Input id="def-vw" type="number" value={String((value.viewport as Obj | undefined)?.width ?? 1280)} onChange={(e) => onChange({ ...value, viewport: { ...(value.viewport as Obj), width: Number(e.target.value) } })} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="def-vh">Cao (px)</Label>
              <Input id="def-vh" type="number" value={String((value.viewport as Obj | undefined)?.height ?? 800)} onChange={(e) => onChange({ ...value, viewport: { ...(value.viewport as Obj), height: Number(e.target.value) } })} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="def-trace">Ghi trace</Label>
              <NativeSelect id="def-trace" value={String(value.trace ?? "on_failure")} onChange={(e) => onChange({ ...value, trace: e.target.value })}>
                <option value="off">Không</option>
                <option value="on_failure">Khi lỗi</option>
                <option value="always">Luôn luôn</option>
              </NativeSelect>
            </div>
          </div>
        ) : (
          <span />
        )}
        <Button type="button" variant="outline" size="sm" onClick={toggleJson}>
          {jsonMode ? "Áp dụng JSON và quay lại" : "Sửa dạng JSON"}
        </Button>
      </div>

      {jsonMode ? (
        <div className="grid gap-1.5">
          <Label htmlFor="def-json">Định nghĩa JSON</Label>
          <Textarea id="def-json" rows={18} className="font-mono text-xs" value={jsonText} onChange={(e) => setJsonText(e.target.value)} />
          {jsonError && (
            <p role="alert" className="text-xs text-status-failed">
              {jsonError}
            </p>
          )}
        </div>
      ) : (
        <>
          <ol className="grid grid-cols-1 gap-3" aria-label="Các bước">
            {steps.map((s, i) => (
              <StepShell
                key={`${rev}-${i}`}
                index={i}
                total={steps.length}
                title={`${String(s.name ?? "")}${kind === "api" ? ` · ${String(s.method ?? "GET")} ${String(s.url ?? "")}` : ` · ${WEB_ACTION_LABEL[String(s.action)] ?? ""}`}`}
                onMove={(d) => restructure(moveItem(steps, i, d))}
                onDuplicate={() => restructure([...steps.slice(0, i + 1), structuredClone(s), ...steps.slice(i + 1)])}
                onRemove={() => restructure(steps.filter((_, j) => j !== i))}
              >
                {kind === "api" ? (
                  <ApiStepFields id={`s${i}`} step={s} onChange={(ns) => setSteps(steps.map((x, j) => (j === i ? ns : x)))} />
                ) : (
                  <WebStepFields id={`s${i}`} step={s} onChange={(ns) => setSteps(steps.map((x, j) => (j === i ? ns : x)))} />
                )}
              </StepShell>
            ))}
          </ol>
          <Button
            type="button"
            variant="outline"
            className="w-fit"
            onClick={() =>
              setSteps([
                ...steps,
                kind === "api"
                  ? { name: `Bước ${steps.length + 1}`, method: "GET", url: "/", assertions: [{ type: "status", equals: 200 }] }
                  : { name: `Bước ${steps.length + 1}`, action: "click", selector: "" },
              ])
            }
          >
            <Plus /> Thêm bước
          </Button>
        </>
      )}
    </div>
  );
}
