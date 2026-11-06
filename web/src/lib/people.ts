import type { PersonRef } from "@/api";
import { tr } from "@/i18n/runtime";

/** A person as the API names them, or the whole household when it names nobody. */
export const personName = (person: PersonRef | null | undefined): string => person?.name ?? tr("household-everyone");
