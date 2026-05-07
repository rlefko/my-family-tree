import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/api/client";

export type PersonRow = {
  id: string;
  display_name: string;
  sex: string;
  surname?: string | null;
  given_names?: string | null;
};

export type PeopleList = { items: PersonRow[] };

export function usePeople(query?: string) {
  return useQuery({
    queryKey: ["people", query ?? ""],
    queryFn: () =>
      apiFetch<PeopleList>(`/api/v1/people${query ? `?q=${encodeURIComponent(query)}` : ""}`),
  });
}

export function usePerson(personId: string | undefined) {
  return useQuery({
    queryKey: ["people", personId],
    enabled: Boolean(personId),
    queryFn: () => apiFetch<PersonRow>(`/api/v1/people/${personId}`),
  });
}
