import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/api/client";

export type ProposalRow = {
  id: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  status: string;
  rationale: string | null;
  confidence: number;
  payload: Record<string, unknown> | null;
  apply_error: string | null;
};

type ProposalListResp = { items: ProposalRow[] };

export function useProposals(status: string | null = "pending") {
  return useQuery({
    queryKey: ["proposals", status ?? "all"],
    queryFn: () => {
      const qs = status ? `?status=${encodeURIComponent(status)}` : "";
      return apiFetch<ProposalListResp>(`/api/v1/proposals${qs}`);
    },
    refetchInterval: 5_000,
  });
}

export function useApproveProposal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (proposalId: string) =>
      apiFetch<ProposalRow>(`/api/v1/proposals/${proposalId}/approve`, {
        method: "POST",
        body: JSON.stringify({ by: "user" }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["proposals"] }),
  });
}

export function useRejectProposal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (proposalId: string) =>
      apiFetch<ProposalRow>(`/api/v1/proposals/${proposalId}/reject`, {
        method: "POST",
        body: JSON.stringify({ by: "user" }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["proposals"] }),
  });
}

export type ApproveBatchResultRow = {
  proposal_id: string;
  status: string;
  target_id: string | null;
  error: string | null;
};

export type ApproveBatchResult = { results: ApproveBatchResultRow[] };

export function useApproveBatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) =>
      apiFetch<ApproveBatchResult>("/api/v1/proposals/approve_batch", {
        method: "POST",
        body: JSON.stringify({ ids, by: "user" }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["proposals"] }),
  });
}
