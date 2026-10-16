import { useQuery } from "@tanstack/react-query";
import { api, type AIStatus } from "@/lib/api";

export function useAIStatus() {
  return useQuery({ queryKey: ["ai-status"], queryFn: () => api<AIStatus>("/api/ai/status"), staleTime: 60_000 });
}
