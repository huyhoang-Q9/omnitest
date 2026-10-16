import {
  Bot,
  ClipboardList,
  FileBarChart,
  FolderKanban,
  Layers,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  PlayCircle,
  Radio,
  Server,
  Settings,
  X,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useLogout, useMe } from "@/hooks/auth";
import { cn } from "@/lib/utils";

type NavItem = { to: string; key: string; icon: typeof LayoutDashboard; phase?: string };

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "groupOverview",
    items: [
      { to: "/", key: "dashboard", icon: LayoutDashboard },
      { to: "/projects", key: "projects", icon: FolderKanban },
      { to: "/environments", key: "environments", icon: Server },
    ],
  },
  {
    group: "groupTesting",
    items: [
      { to: "/test-cases", key: "testCases", icon: ListChecks },
      { to: "/test-suites", key: "testSuites", icon: Layers },
      { to: "/test-runs", key: "testRuns", icon: PlayCircle },
      { to: "/live", key: "liveExecution", icon: Radio },
      { to: "/reports", key: "reports", icon: FileBarChart },
      { to: "/ai", key: "aiAssistant", icon: Bot },
    ],
  },
  { group: "groupSystem", items: [{ to: "/settings", key: "settings", icon: Settings }] },
];

function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  return (
    <nav aria-label="Điều hướng chính" className="flex flex-1 flex-col gap-5 overflow-y-auto px-3 py-4">
      {NAV.map((g) => (
        <div key={g.group} className="space-y-1">
          <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-sidebar-muted">
            {t(`nav.${g.group}`)}
          </p>
          {g.items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm text-sidebar-foreground/85 transition-colors hover:bg-sidebar-active hover:text-white",
                  isActive && "bg-sidebar-active font-medium text-white",
                )
              }
            >
              <item.icon className="size-4 shrink-0" aria-hidden />
              <span className="flex-1 truncate">{t(`nav.${item.key}`)}</span>
              {item.phase && (
                <span
                  className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-sidebar-muted"
                  title={t("common.comingIn", { phase: item.phase })}
                >
                  {item.phase}
                </span>
              )}
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  );
}

function Brand() {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2.5 px-6 py-5">
      <div className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
        <ClipboardList className="size-4" aria-hidden />
      </div>
      <div className="leading-tight">
        <p className="font-semibold text-white">{t("app.name")}</p>
        <p className="text-xs text-sidebar-muted">{t("app.tagline")}</p>
      </div>
    </div>
  );
}

export function AppLayout() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const onLogout = () =>
    logout.mutate(undefined, {
      onSuccess: () => {
        toast.success("Đã đăng xuất");
        navigate("/login", { replace: true });
      },
    });

  return (
    <div className="min-h-dvh lg:pl-64">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col bg-sidebar lg:flex">
        <Brand />
        <SidebarNav />
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85%] flex-col bg-sidebar">
            <div className="flex items-center justify-between pr-3">
              <Brand />
              <Button
                variant="ghost"
                size="icon"
                className="text-sidebar-foreground hover:bg-sidebar-active"
                onClick={() => setOpen(false)}
                aria-label="Đóng menu"
              >
                <X />
              </Button>
            </div>
            <SidebarNav onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}

      <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b bg-card/90 px-4 backdrop-blur sm:px-6">
        <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setOpen(true)} aria-label={t("nav.openMenu")}>
          <Menu />
        </Button>
        <div className="flex-1" />
        {me && (
          <div className="flex items-center gap-3">
            <div className="hidden text-right text-sm leading-tight sm:block">
              <p className="font-medium">{me.full_name}</p>
              <p className="text-xs text-muted-foreground">
                {me.email}
                {me.is_system_admin && " · Quản trị hệ thống"}
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={onLogout} loading={logout.isPending}>
              <LogOut /> <span className="hidden sm:inline">{t("nav.logout")}</span>
            </Button>
          </div>
        )}
      </header>

      <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
        <Outlet />
      </main>
    </div>
  );
}
