import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/api/client";

export type ConversationRow = {
  id: string;
  title: string | null;
  last_message_at: string | null;
  created_at: string;
};

export type ConversationListResp = { items: ConversationRow[] };

export type AssistantBlock =
  | {
      type: "tool_use";
      id: string;
      name: string;
      input: unknown;
      output: unknown;
      is_error: boolean;
    }
  | { type: "text"; text: string }
  | { type: "proposals_summary"; proposal_ids: string[] };

export type UserBlock = { type: "text"; text: string };

export type MessageRow = {
  id: string;
  role: "user" | "assistant" | "tool" | "system";
  content: (AssistantBlock | UserBlock)[];
  created_at: string;
  input_tokens: number | null;
  output_tokens: number | null;
  proposal_ids: string[];
};

export type ConversationDetail = {
  id: string;
  title: string | null;
  last_message_at: string | null;
  messages: MessageRow[];
};

export function useConversations() {
  return useQuery({
    queryKey: ["conversations"],
    queryFn: () => apiFetch<ConversationListResp>("/api/v1/conversations"),
  });
}

export async function fetchConversation(id: string): Promise<ConversationDetail> {
  return apiFetch<ConversationDetail>(`/api/v1/conversations/${id}`);
}
