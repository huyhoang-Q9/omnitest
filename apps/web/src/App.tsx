import { lazy } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppLayout } from "@/components/app-layout";
import { ErrorState, LoadingState } from "@/components/states";
import { useMe } from "@/hooks/auth";
import { LoginPage } from "@/pages/LoginPage";

// Mỗi trang là một chunk riêng, tải khi cần (trang đăng nhập tải ngay).
const page = <K extends string>(load: () => Promise<Record<K, React.ComponentType>>, name: K) =>
  lazy(() => load().then((m) => ({ default: m[name] })));
const AIAssistantPage = page(() => import("@/pages/AIAssistantPage"), "AIAssistantPage");
const DashboardPage = page(() => import("@/pages/DashboardPage"), "DashboardPage");
const EnvironmentDetailPage = page(() => import("@/pages/EnvironmentDetailPage"), "EnvironmentDetailPage");
const EnvironmentsPage = page(() => import("@/pages/EnvironmentsPage"), "EnvironmentsPage");
const ProjectDetailPage = page(() => import("@/pages/ProjectDetailPage"), "ProjectDetailPage");
const ProjectsPage = page(() => import("@/pages/ProjectsPage"), "ProjectsPage");
const ReportsPage = page(() => import("@/pages/ReportsPage"), "ReportsPage");
const LivePage = page(() => import("@/pages/LivePage"), "LivePage");
const RunDetailPage = page(() => import("@/pages/RunDetailPage"), "RunDetailPage");
const SettingsPage = page(() => import("@/pages/SettingsPage"), "SettingsPage");
const TestCaseEditorPage = page(() => import("@/pages/TestCaseEditorPage"), "TestCaseEditorPage");
const TestCasesPage = page(() => import("@/pages/TestCasesPage"), "TestCasesPage");
const TestRunsPage = page(() => import("@/pages/TestRunsPage"), "TestRunsPage");
const TestSuitesPage = page(() => import("@/pages/TestSuitesPage"), "TestSuitesPage");
const SuiteDetailPage = page(() => import("@/pages/TestSuitesPage"), "SuiteDetailPage");

function RequireAuth() {
  const me = useMe();
  const location = useLocation();
  if (me.isPending)
    return (
      <div className="mx-auto max-w-md p-10">
        <LoadingState />
      </div>
    );
  if (me.isError)
    return (
      <div className="mx-auto max-w-md p-10">
        <ErrorState message={me.error.message} onRetry={() => me.refetch()} />
      </div>
    );
  if (!me.data) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <AppLayout />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route index element={<DashboardPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:projectId" element={<ProjectDetailPage />} />
        <Route path="environments" element={<EnvironmentsPage />} />
        <Route path="environments/:environmentId" element={<EnvironmentDetailPage />} />
        <Route path="test-cases" element={<TestCasesPage />} />
        <Route path="test-cases/new" element={<TestCaseEditorPage />} />
        <Route path="test-cases/:caseId" element={<TestCaseEditorPage key="edit" />} />
        <Route path="test-suites" element={<TestSuitesPage />} />
        <Route path="test-suites/:suiteId" element={<SuiteDetailPage />} />
        <Route path="test-runs" element={<TestRunsPage />} />
        <Route path="test-runs/:runId" element={<RunDetailPage />} />
        <Route path="live" element={<LivePage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="ai" element={<AIAssistantPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<ErrorState message="Không tìm thấy trang." />} />
      </Route>
    </Routes>
  );
}
