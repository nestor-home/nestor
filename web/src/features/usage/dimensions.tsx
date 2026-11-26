/** Every value spending is split by, as people read it: its name, its mark, and its colour, which follows it
 * whatever the filters (a person keeps their colour when the others are filtered out). */
import { useQuery } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import {
  AudioLines,
  BellRing,
  BookMarked,
  CircleDashed,
  Heading,
  Megaphone,
  MessageSquareText,
  Search,
  Workflow,
} from "lucide-react";
import type { ReactNode } from "react";
import { type CallPurpose, peopleQuery, type UsageDimension, type UsageGroup, usagePricesQuery } from "@/api";
import { callPurposeValues, costBasisValues, modelTypeValues, outcomeValues } from "@/api/schema.gen";
import { Avatar } from "@/components/marks";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { BrandMark, type BrandSlug, brandName, brandOf, KindMark, kindName } from "@/lib/brands";
import { useCan, useMe } from "@/lib/session";
import { capital } from "@/lib/utils";

/** How many series have a colour of their own (`--series-1…6`); the rest share one. */
export const SERIES = 6;
export const OTHER = "var(--rule-strong)";

export const PURPOSE_ICON: Record<CallPurpose, LucideIcon> = {
  turn: MessageSquareText,
  notification: Megaphone,
  title: Heading,
  alert: BellRing,
  consolidation: BookMarked,
  indexing: Search,
  enrollment: AudioLines,
  task: Workflow,
  search: Search,
  unattributed: CircleDashed,
};

/** The brand of a model: its maker when its provider routes it (`anthropic/claude-…` through OpenRouter), else its
 * provider's. */
export function modelBrand(served: string | null | undefined, provider: string): BrandSlug | null {
  const maker = served?.includes("/") ? served.split("/")[0] : null;
  return (maker ? brandOf(maker) : null) ?? brandOf(provider);
}

export interface Dimensions {
  label: (dimension: UsageDimension, key: string | null, group?: UsageGroup) => string;
  mark: (dimension: UsageDimension, key: string | null, group?: UsageGroup) => ReactNode;
  /** A value's colour: by the household's people and models in their own order, the server's values in theirs,
   * anything else in `ranked`'s order (what the period spent on it, the costliest first). */
  colour: (dimension: UsageDimension, key: string | null, ranked?: readonly (string | null)[]) => string;
}

export function useDimensions(): Dimensions {
  const t = useT();
  const me = useMe();
  const people = useQuery({ ...peopleQuery, enabled: useCan("people:read") }).data ?? [];
  const prices = useQuery(usagePricesQuery).data;
  const served = new Map(prices?.prices.map((p) => [p.consumer, p]) ?? []);
  const orders: Partial<Record<UsageDimension, readonly (string | null)[]>> = {
    consumer: prices?.prices.map((p) => p.consumer),
    person: [...people.map((p) => p.id), null],
    purpose: callPurposeValues,
    kind: modelTypeValues,
    basis: costBasisValues,
    outcome: outcomeValues,
  };
  const nameOf = (id: string) => people.find((p) => p.id === id)?.name ?? id;
  const brandMark = (provider: string | null, model?: string | null) => {
    const brand = provider ? modelBrand(model, provider) : null;
    return brand ? <BrandMark brand={brand} label={false} className="size-5" /> : <Dot />;
  };

  return {
    label: (dimension, key, group) => {
      switch (dimension) {
        case "person":
          return key === null ? t("usage-own-work", { assistant: me.assistant }) : (group?.person?.name ?? nameOf(key));
        case "purpose":
          return capital(tr("usage-purpose", { purpose: key ?? "unattributed" }));
        case "kind":
          return capital(tr("usage-kind", { kind: key ?? "" }));
        case "basis":
          return capital(tr("usage-basis", { basis: key ?? "unknown" }));
        case "outcome":
          return capital(tr("usage-outcome", { outcome: key ?? "ok" }));
        case "channel":
          return key === null ? t("usage-no-channel") : kindName(key);
        case "provider": {
          const brand = key ? brandOf(key) : null;
          return brand ? brandName(brand) : (key ?? "-");
        }
        default:
          return key ?? "-";
      }
    },
    mark: (dimension, key, group) => {
      switch (dimension) {
        case "person":
          return key === null ? (
            <span aria-hidden="true" className="grid size-6 place-items-center rounded-full bg-ink text-paper">
              <span className="size-2 rounded-full bg-ember" />
            </span>
          ) : (
            <Avatar name={group?.person?.name ?? nameOf(key)} size="sm" className="size-6" />
          );
        case "consumer": {
          const model = key ? served.get(key) : undefined;
          return brandMark(model?.provider ?? null, model?.model);
        }
        case "provider":
          return brandMark(key);
        case "channel":
          return key ? <KindMark kind={key} label={false} className="size-5" /> : <Dot />;
        case "purpose": {
          const Icon = PURPOSE_ICON[(key ?? "unattributed") as CallPurpose] ?? CircleDashed;
          return <Icon aria-hidden="true" className="size-4.5 text-ink-muted" />;
        }
        default:
          return <Dot />;
      }
    },
    colour: (dimension, key, ranked = []) => {
      const slot = (orders[dimension] ?? ranked).indexOf(key);
      return slot >= 0 && slot < SERIES ? `var(--series-${slot + 1})` : OTHER;
    },
  };
}

function Dot() {
  return <span aria-hidden="true" className="size-2 rounded-full bg-rule-strong" />;
}
