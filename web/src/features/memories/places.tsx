/**
 * Where a memory is filed, as the admin names it: a person, the house, the household's shared life, or a project
 * or a topic the agent named (`roof-works` reads "Roof works").
 */
import type { Memory, Place, Shelf } from "@/api";
import { Avatar } from "@/components/marks";
import type { useT } from "@/i18n";
import { SHELF_ICON } from "@/lib/icons";

/** A name the agent wrote in lowercase words joined by hyphens, as a person reads it. */
export const readable = (name: string): string => {
  const words = name.replace(/-+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

/** What a place is called: the person's name, Home, Household, or the project's or topic's name. */
export function placeName(t: ReturnType<typeof useT>, place: Place): string {
  switch (place.shelf) {
    case "people":
      return place.person?.name ?? place.name ?? "";
    case "home":
      return t("mem-shelf-home");
    case "household":
      return t("mem-shelf-household");
    default:
      return readable(place.name ?? "");
  }
}

/** A place's mark, inline beside its name: the person's avatar, or its shelf's icon. */
export function PlaceIcon({ place, name }: { place: Place; name: string }) {
  if (place.shelf === "people") return <Avatar name={name} size="xs" />;
  const Icon = SHELF_ICON[place.shelf];
  return <Icon className="size-3.5 shrink-0" aria-hidden="true" />;
}

/** Whether a shelf holds places the agent names. */
export const named = (shelf: Shelf): shelf is "projects" | "topics" => shelf === "projects" || shelf === "topics";

const SHELF_ORDER: Record<Shelf, number> = { people: 0, home: 1, household: 2, projects: 3, topics: 4 };

/**
 * The places of `memories`, each with its memories: the people in the household's order (`people`, ids), then
 * Home, Household, the projects and the topics by name.
 */
export function byPlace(memories: readonly Memory[], people: readonly string[]): { place: Place; list: Memory[] }[] {
  const groups = new Map<string, { place: Place; list: Memory[] }>();
  for (const m of memories) {
    const group = groups.get(m.place.path) ?? { place: m.place, list: [] };
    group.list.push(m);
    groups.set(m.place.path, group);
  }
  const rank = (place: Place) => {
    const at = people.indexOf(place.name ?? "");
    return at === -1 ? people.length : at;
  };
  return [...groups.values()].sort(
    (a, b) =>
      SHELF_ORDER[a.place.shelf] - SHELF_ORDER[b.place.shelf] ||
      (a.place.shelf === "people" ? rank(a.place) - rank(b.place) : 0) ||
      (a.place.name ?? "").localeCompare(b.place.name ?? ""),
  );
}
