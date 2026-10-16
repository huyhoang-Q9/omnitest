import { useQuery } from "@tanstack/react-query";
import { api, type Adapter } from "@/lib/api";

/** Trạng thái sandbox script code trên máy chủ (từ danh sách adapter). */
export function useSandboxStatus() {
  return useQuery({
    queryKey: ["adapters"],
    queryFn: () => api<Adapter[]>("/api/adapters"),
    staleTime: 60_000,
    select: (list) => list.find((a) => a.test_kinds.includes("script")),
  });
}
