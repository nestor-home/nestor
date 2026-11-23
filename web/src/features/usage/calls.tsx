/** Every call the period's filters keep, newest first, a page at a time; one opens in a sheet. */
import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { type UsageCall, type UsageQuery, usageCallsQuery } from "@/api";
import { RowList, Section } from "@/components/page";
import { Empty, Failure } from "@/components/states";
import { Tag } from "@/components/status";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { moment } from "@/lib/dates";
import { capital } from "@/lib/utils";
import { CallSheet } from "./call-sheet";
import type { Dimensions } from "./dimensions";
import { money } from "./format";

export function Calls({ query, dimensions }: { query: UsageQuery; dimensions: Dimensions }) {
  const t = useT();
  const calls = useInfiniteQuery(usageCallsQuery(query));
  const [open, setOpen] = useState<UsageCall | null>(null);
  const [shown, setShown] = useState(false);
  const rows = calls.data?.pages.flatMap((p) => p.calls) ?? [];
  return (
    <Section title={t("usage-calls-title")}>
      {calls.isError ? <Failure error={calls.error} retry={() => void calls.refetch()} /> : null}
      {rows.length ? (
        <div className="grid gap-3">
          <RowList>
            {rows.map((call) => (
              <li key={call.id}>
                <Row
                  call={call}
                  dimensions={dimensions}
                  onOpen={() => {
                    setOpen(call);
                    setShown(true);
                  }}
                />
              </li>
            ))}
          </RowList>
          {calls.hasNextPage ? (
            <Button
              variant="ghost"
              className="justify-self-center"
              onClick={() => void calls.fetchNextPage()}
              disabled={calls.isFetchingNextPage}
            >
              {t("usage-calls-more")}
            </Button>
          ) : null}
        </div>
      ) : calls.isPending ? (
        <div className="surface h-64 animate-pulse" />
      ) : (
        <Empty>{t("usage-empty")}</Empty>
      )}
      <CallSheet
        call={open}
        open={shown}
        onOpenChange={setShown}
        onClosed={() => setOpen(null)}
        dimensions={dimensions}
      />
    </Section>
  );
}

function Row({ call, dimensions, onOpen }: { call: UsageCall; dimensions: Dimensions; onOpen: () => void }) {
  const person = call.person?.id ?? null;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="grid w-full grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5 px-4 py-3 text-left transition-colors hover:bg-paper-sunken/60 sm:grid-cols-[1.5rem_minmax(0,1.3fr)_minmax(0,1fr)_8rem_6.5rem] sm:px-5"
    >
      <span className="grid size-6 place-items-center">{dimensions.mark("consumer", call.consumer)}</span>
      <span className="min-w-0">
        <span className="block truncate text-body font-medium text-ink">
          {capital(tr("usage-purpose", { purpose: call.purpose }))}
          {call.outcome !== "ok" ? (
            <span className="ml-2 text-meta font-normal text-amber">
              {tr("usage-outcome", { outcome: call.outcome })}
            </span>
          ) : null}
        </span>
        <span className="block truncate text-meta text-ink-muted">
          {call.consumer}
          {call.served ? ` · ${call.served}` : ""}
        </span>
      </span>
      <span className="hidden min-w-0 items-center gap-2 truncate text-meta text-ink-muted sm:flex">
        {dimensions.mark("person", person)}
        <span className="truncate">{dimensions.label("person", person)}</span>
      </span>
      <span className="hidden text-meta text-ink-faint tabular sm:block">{moment(call.at)}</span>
      <span className="text-right text-body font-semibold text-ink tabular">
        {call.cost_nusd === null || call.cost_nusd === undefined ? (
          <Tag tone="attention">{tr("usage-basis", { basis: "unknown" })}</Tag>
        ) : (
          money(call.cost_nusd)
        )}
      </span>
    </button>
  );
}
