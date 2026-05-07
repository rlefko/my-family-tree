import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/api/client";

export type HealthStatus = {
  status: string;
  db: string;
  s3: string;
  llm: { openai: string; anthropic: string };
};

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => apiFetch<HealthStatus>("/healthz"),
    refetchInterval: 30_000,
  });
}
