/** Every value spending is split by, as people read it: its name, its mark, and its colour, which follows it
 * whatever the filters (a person keeps their colour when the others are filtered out). */
import { useQuery } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import {
  AudioLines,
  BookMarked,
  CircleDashed,
  Heading,
  Megaphone,
  MessageSquareText,
  Radar,
  Search,
  Workflow,
} from "lucide-react";
import type { ReactNode } from "react";
import {
  type CallPurpose,
  peopleQuery,
  type UsageDimension,
  type UsageGroup,
  usageGroupsQuery,
  usagePricesQuery,
} from "@/api";
import { callPurposeValues, consumerKindValues, costBasisValues, outcomeValues } from "@/api/schema.gen";
import { Avatar } from "@/components/marks";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { BrandMark, brandName, brandOf, KindMark, kindName } from "@/lib/brands";
import { useCan, useMe } from "@/lib/session";
import type { Period } from "./search";

const SERIES = 6;
export const OTHER = "var(--rule-strong)";
export const seriesColour = (slot: number) => (slot < SERIES ? `var(--series-${slot + 1})` : OTHER);

export const PURPOSE_ICON: Record<CallPurpose, LucideIcon> = {
  turn: MessageSquareText,
  notification: Megaphone,
  title: Heading,
  watch: Radar,
  consolidation: BookMarked,
  indexing: Search,
  enrollment: AudioLines,
  task: Workflow,
  search: Search,
  unattributed: CircleDashed,
};

/** The model's maker when its provider routes it (`anthropic/claude-…` through OpenRouter), else the provider. */
export function makerOf(served: string | null | undefined, provider: string): string {
  const maker = served?.includes("/") ? served.split("/")[0] : null;
  return maker && brandOf(maker) ? maker : provider;
}

/** A label as it opens a line: the server's labels are written to sit inside a sentence. */
export const capital = (text: string) => text.charAt(0).toLocaleUpperCase() + text.slice(1);

export interface Dimensions {
  label: (dimension: UsageDimension, key: string | null, group?: UsageGroup) => string;
  mark: (dimension: UsageDimension, key: string | null, group?: UsageGroup) => ReactNode;
  colour: (dimension: UsageDimension, key: string | null) => string;
}

/** How each value reads, and its colour: the household's people and the configured models in their own order, the
 * server's values in theirs, anything else by what it cost over the period, the costliest first. */
export function useDimensions(period: Period, split: UsageDimension): Dimensions {
  const t = useT();
  const me = useMe();
  const people = useQuery({ ...peopleQuery, enabled: useCan("people:read") }).data ?? [];
  const prices = useQuery(usagePricesQuery).data;
  const spread = useQuery(
    usageGroupsQuery({ since: period.since.toISOString(), until: period.until.toISOString(), by: split }),
  ).data;
  const served = new Map(prices?.prices.map((p) => [p.consumer, p]) ?? []);
  const orders: Partial<Record<UsageDimension, (string | null)[]>> = {
    consumer: prices?.prices.map((p) => p.consumer),
    person: [...people.map((p) => p.id), null],
    purpose: [...callPurposeValues],
    kind: [...consumerKindValues],
    basis: [...costBasisValues],
    outcome: [...outcomeValues],
  };
  const fallback = spread?.groups.map((g) => g.key) ?? [];
  const nameOf = (id: string) => people.find((p) => p.id === id)?.name ?? id;

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
          const brand = brandOf(makerOf(model?.model, model?.provider ?? ""));
          return brand ? <BrandMark brand={brand} label={false} className="size-5" /> : <Dot />;
        }
        case "provider": {
          const brand = key ? brandOf(key) : null;
          return brand ? <BrandMark brand={brand} label={false} className="size-5" /> : <Dot />;
        }
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
    colour: (dimension, key) => {
      const order = orders[dimension] ?? fallback;
      const slot = order.indexOf(key);
      return slot < 0 ? OTHER : seriesColour(slot);
    },
  };
}

function Dot() {
  return <span aria-hidden="true" className="size-2 rounded-full bg-rule-strong" />;
}
