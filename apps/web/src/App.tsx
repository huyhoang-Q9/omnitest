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
import { SettingsPage } from "@/pages/SettingsPage";

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
  { path: "/test-cases", title: "Test case", phase: "Giai đoạn 3", description: "Tạo, sửa, sao chép, phân loại test case API và Web; import/export CSV, Excel; lịch sử thay đổi." },
  { path: "/test-suites", title: "Test suite", phase: "Giai đoạn 3", description: "Nhóm test case thành suite và chạy theo suite." },
  { path: "/test-runs", title: "Lần chạy", phase: "Giai đoạn 3", description: "Danh sách lần chạy, trạng thái, thời gian, log và kết quả từng bước." },
  { path: "/live", title: "Đang thực thi", phase: "Giai đoạn 3", description: "Theo dõi lần chạy theo thời gian thực và hủy an toàn." },
  { path: "/reports", title: "Báo cáo", phase: "Giai đoạn 4", description: "Báo cáo theo dự án, suite, môi trường; xuất HTML, CSV, Excel." },
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
        <Route path="settings" element={<SettingsPage />} />
        {PLANNED.map((p) => (
          <Route key={p.path} path={p.path.slice(1)} element={<ComingSoonPage {...p} />} />
        ))}
        <Route path="*" element={<ErrorState message="Không tìm thấy trang." />} />
      </Route>
    </Routes>
  );
}
