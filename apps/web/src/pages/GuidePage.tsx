import { BookOpen, CheckCircle2, Circle, ExternalLink, Lightbulb } from "lucide-react";
import { Fragment, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import guide from "@/lib/guide.json";
import { cn } from "@/lib/utils";

type Section = (typeof guide.sections)[number] & { route?: string; image?: string; tips?: string[] };
const SECTIONS = guide.sections as Section[];
const GROUPS = [...new Set(SECTIONS.map((s) => s.group))];
const DONE_KEY = "omnitest.guide.done";

/** Định dạng tối giản trong nội dung hướng dẫn: **đậm** và `mã`. */
function Rich({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) =>
        part.startsWith("**") ? (
          <strong key={i} className="font-semibold">
            {part.slice(2, -2)}
          </strong>
        ) : part.startsWith("`") ? (
          <code key={i} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">
            {part.slice(1, -1)}
          </code>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}

/** Tiến độ "đã làm" chỉ lưu trên trình duyệt này, cho người dùng tự đánh dấu khi đi theo hướng dẫn. */
function useDone() {
  const [done, setDone] = useState<string[]>(() => {
    try {
      const v: unknown = JSON.parse(localStorage.getItem(DONE_KEY) ?? "[]");
      return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
    } catch {
      return [];
    }
  });
  const toggle = (id: string) =>
    setDone((cur) => {
      const next = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
      try {
        localStorage.setItem(DONE_KEY, JSON.stringify(next));
      } catch {
        // Trình duyệt chặn lưu trữ: vẫn dùng được trong phiên hiện tại.
      }
      return next;
    });
  return { done, toggle };
}

function SectionCard({ s, n, done, onToggle }: { s: Section; n: number; done: boolean; onToggle: () => void }) {
  const openable = s.route && s.route !== "/login";
  return (
    <Card id={s.id} className="scroll-mt-20 overflow-hidden">
      <CardContent className="space-y-4 p-5 sm:p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 gap-3">
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary text-sm font-semibold text-primary-foreground" aria-hidden>
              {n}
            </span>
            <div className="min-w-0">
              <h2 className="text-lg font-semibold leading-tight">{s.title}</h2>
              <p className="mt-1 text-sm text-muted-foreground">{s.summary}</p>
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2 pl-11 sm:pl-0">
            {openable && (
              <Button asChild size="sm">
                <Link to={s.route as string}>
                  <ExternalLink /> Mở màn hình này
                </Link>
              </Button>
            )}
            <Button size="sm" variant={done ? "secondary" : "outline"} onClick={onToggle} aria-pressed={done}>
              {done ? <CheckCircle2 className="text-status-passed" /> : <Circle />} {done ? "Đã làm" : "Đánh dấu đã làm"}
            </Button>
          </div>
        </div>

        <div className={cn("grid gap-5", s.image && "lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]")}>
          <ol className="space-y-2.5 text-sm leading-relaxed">
            {s.steps.map((step, i) => (
              <li key={i} className="flex gap-3">
                <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-accent text-[11px] font-semibold text-accent-foreground">
                  {i + 1}
                </span>
                <span className="min-w-0">
                  <Rich text={step} />
                </span>
              </li>
            ))}
          </ol>
          {s.image && (
            <a
              href={`/guide/${s.image}`}
              target="_blank"
              rel="noreferrer"
              className="block self-start overflow-hidden rounded-lg border shadow-xs transition hover:shadow-md"
              title="Mở ảnh cỡ lớn"
            >
              <img
                src={`/guide/${s.image}`}
                alt={`Màn hình: ${s.title}`}
                loading="lazy"
                className="max-h-[28rem] w-full object-cover object-top"
              />
            </a>
          )}
        </div>

        {!!s.tips?.length && (
          <div className="flex gap-3 rounded-lg bg-status-blocked/10 p-3 text-sm">
            <Lightbulb className="mt-0.5 size-4 shrink-0 text-status-blocked" aria-hidden />
            <ul className="space-y-1">
              {s.tips.map((t) => (
                <li key={t}>
                  <Rich text={t} />
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Toc({ done }: { done: string[] }): ReactNode {
  return (
    <nav aria-label="Mục lục hướng dẫn" className="space-y-4 text-sm">
      <p className="text-xs text-muted-foreground">
        Đã làm {done.filter((d) => SECTIONS.some((s) => s.id === d)).length}/{SECTIONS.length} phần
      </p>
      {GROUPS.map((g) => (
        <div key={g} className="space-y-1">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{g}</p>
          {SECTIONS.filter((s) => s.group === g).map((s) => {
            const n = SECTIONS.indexOf(s) + 1;
            return (
              <a key={s.id} href={`#${s.id}`} className="flex items-center gap-2 rounded px-2 py-1 hover:bg-muted">
                {done.includes(s.id) ? (
                  <CheckCircle2 className="size-3.5 shrink-0 text-status-passed" aria-label="Đã làm" />
                ) : (
                  <span className="w-3.5 shrink-0 text-center text-xs text-muted-foreground">{n}</span>
                )}
                <span className="truncate">{s.title}</span>
              </a>
            );
          })}
        </div>
      ))}
      <a href="#hoi-dap" className="block rounded px-2 py-1 hover:bg-muted">
        Hỏi đáp
      </a>
    </nav>
  );
}

/** Hướng dẫn sử dụng từng bước, có ảnh màn hình thật và nút mở đúng màn hình để vừa đọc vừa làm. */
export function GuidePage() {
  const { done, toggle } = useDone();
  return (
    <>
      <PageHeader title={guide.title} description={guide.intro} />
      <div className="grid gap-6 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <aside className="hidden lg:block">
          <div className="sticky top-20 max-h-[calc(100dvh-6rem)] overflow-y-auto pr-2">
            <Toc done={done} />
          </div>
        </aside>
        <div className="min-w-0 space-y-8">
          <details className="rounded-lg border bg-card p-4 lg:hidden">
            <summary className="flex cursor-pointer items-center gap-2 font-medium">
              <BookOpen className="size-4" /> Mục lục
            </summary>
            <div className="mt-3">
              <Toc done={done} />
            </div>
          </details>
          {GROUPS.map((g) => (
            <section key={g} className="space-y-4" aria-label={g}>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">{g}</h2>
              {SECTIONS.filter((s) => s.group === g).map((s) => (
                <SectionCard key={s.id} s={s} n={SECTIONS.indexOf(s) + 1} done={done.includes(s.id)} onToggle={() => toggle(s.id)} />
              ))}
            </section>
          ))}
          <section id="hoi-dap" className="scroll-mt-20 space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Hỏi đáp</h2>
            {guide.faq.map((f) => (
              <details key={f.q} className="rounded-lg border bg-card p-4">
                <summary className="cursor-pointer font-medium">{f.q}</summary>
                <p className="mt-2 text-sm text-muted-foreground">{f.a}</p>
              </details>
            ))}
          </section>
        </div>
      </div>
    </>
  );
}
