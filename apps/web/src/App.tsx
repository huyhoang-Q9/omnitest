import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppLayout } from "@/components/app-layout";
import { ErrorState, LoadingState } from "@/components/states";
import { useMe } from "@/hooks/auth";
import { ComingSoonPage } from "@/pages/ComingSoonPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { EnvironmentDetailPage } from "@/pages/EnvironmentDetailPage";
import { EnvironmentsPage } from "@/pages/EnvironmentsPage";
import { LoginPage } from "@/pages/LoginPage";
import { ProjectDetailPage } from "@/pages/ProjectDetailPage";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { LivePage } from "@/pages/LivePage";
import { RunDetailPage } from "@/pages/RunDetailPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { TestCaseEditorPage } from "@/pages/TestCaseEditorPage";
import { TestCasesPage } from "@/pages/TestCasesPage";
import { TestRunsPage } from "@/pages/TestRunsPage";
import { SuiteDetailPage, TestSuitesPage } from "@/pages/TestSuitesPage";

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

const PLANNED = [
  { path: "/ai", title: "Trợ lý AI", phase: "Giai đoạn 5", description: "Đề xuất test case, sinh script nháp và phân tích lỗi; luôn cần người dùng duyệt." },
];

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
        <Route path="settings" element={<SettingsPage />} />
        {PLANNED.map((p) => (
          <Route key={p.path} path={p.path.slice(1)} element={<ComingSoonPage {...p} />} />
        ))}
        <Route path="*" element={<ErrorState message="Không tìm thấy trang." />} />
      </Route>
    </Routes>
  );
}
