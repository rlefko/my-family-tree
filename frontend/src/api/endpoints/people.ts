import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/api/client";

export type PersonRow = {
  id: string;
  display_name: string;
  sex: "male" | "female" | "unknown";
  surname: string | null;
  given_names: string | null;
  birth_text: string | null;
  death_text: string | null;
  is_living: boolean;
  status: string;
  relationship_count: number;
  document_count: number;
};

export type PeopleList = { items: PersonRow[] };

export type PersonDetail = {
  id: string;
  display_name: string;
  sex: "male" | "female" | "unknown";
  surname: string | null;
  surname_at_birth: string | null;
  given_names: string | null;
  suffix: string | null;
  birth_text: string | null;
  death_text: string | null;
  birth_place_id: string | null;
  death_place_id: string | null;
  is_living: boolean;
  notes_md: string | null;
  status: string;
  aliases: string[];
};

export type RelationshipEdge = {
  id: string;
  type: string;
  direction: "outgoing" | "incoming";
  other: PersonRow;
  confidence: number;
};

export type RelationshipsList = { items: RelationshipEdge[] };

export type DocumentRef = {
  id: string;
  title: string | null;
  kind: string;
  citation: string | null;
  claim_count: number;
};

export type DocumentsList = { items: DocumentRef[] };

export function usePeople(query?: string) {
  return useQuery({
    queryKey: ["people", query ?? ""],
    queryFn: () =>
      apiFetch<PeopleList>(`/api/v1/people${query ? `?q=${encodeURIComponent(query)}` : ""}`),
  });
}

export function usePerson(personId: string | null | undefined) {
  return useQuery({
    queryKey: ["people", personId, "detail"],
    enabled: Boolean(personId),
    queryFn: () => apiFetch<PersonDetail>(`/api/v1/people/${personId}`),
  });
}

export function usePersonRelationships(personId: string | null | undefined) {
  return useQuery({
    queryKey: ["people", personId, "relationships"],
    enabled: Boolean(personId),
    queryFn: () =>
      apiFetch<RelationshipsList>(`/api/v1/people/${personId}/relationships`),
  });
}

export function usePersonDocuments(personId: string | null | undefined) {
  return useQuery({
    queryKey: ["people", personId, "documents"],
    enabled: Boolean(personId),
    queryFn: () => apiFetch<DocumentsList>(`/api/v1/people/${personId}/documents`),
  });
}

export function useDeletePerson() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (personId: string) =>
      apiFetch<{ proposal_id: string; status: string }>(
        `/api/v1/people/${personId}`,
        { method: "DELETE" },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["people"] });
      qc.invalidateQueries({ queryKey: ["tree-graph"] });
    },
  });
}

export function useAppendNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ personId, text }: { personId: string; text: string }) =>
      apiFetch<{ proposal_id: string; status: string }>(
        `/api/v1/people/${personId}/notes`,
        { method: "POST", body: JSON.stringify({ notes_md: text }) },
      ),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["people"] });
      qc.invalidateQueries({ queryKey: ["people", vars.personId] });
    },
  });
}

export function useAddRelationship() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      personId,
      otherId,
      type,
      direction,
    }: {
      personId: string;
      otherId: string;
      type: string;
      direction: "outgoing" | "incoming";
    }) =>
      apiFetch<{ proposal_id: string; relationship_id: string }>(
        `/api/v1/people/${personId}/relationships`,
        {
          method: "POST",
          body: JSON.stringify({ other_id: otherId, type, direction }),
        },
      ),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["people"] });
      qc.invalidateQueries({ queryKey: ["people", vars.personId] });
      qc.invalidateQueries({ queryKey: ["people", vars.otherId] });
      qc.invalidateQueries({ queryKey: ["tree-graph"] });
    },
  });
}
