import { useQuery } from "@tanstack/react-query";
import { type Id, type PersonRef, peopleQuery } from "@/api";
import { tr } from "@/i18n/runtime";

/** Names by person id; an unknown id is shown as written, `null` is the whole household. */
export function usePeopleNames(): (id: Id | null | undefined) => string {
  const { data } = useQuery(peopleQuery);
  const names = new Map((data ?? []).map((p) => [p.id, p.name]));
  return (id) => (id ? (names.get(id) ?? id) : tr("household-everyone"));
}

/** A person as the API names them, or the whole household when it names nobody. */
export const personName = (person: PersonRef | null | undefined): string => person?.name ?? tr("household-everyone");
