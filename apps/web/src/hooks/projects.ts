import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api, type Page, type Project } from "@/lib/api";

/** Danh sách dự án người dùng thấy và dự án đang chọn (lưu ở query ?project=). */
export function useProjectSelection() {
  const [params, setParams] = useSearchParams();
  const q = useQuery({
    queryKey: ["projects", { all: true }],
    queryFn: () => api<Page<Project>>("/api/projects?page_size=100"),
  });
  const projects = q.data?.items ?? [];
  const selected = projects.find((p) => p.id === params.get("project")) ?? projects[0];
  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set("project", id);
    next.delete("page");
    setParams(next, { replace: true });
  };
  return { query: q, projects, selected, select };
}

