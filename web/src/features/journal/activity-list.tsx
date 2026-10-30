import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { type JournalFilters, journalLatestQuery } from "@/api";
import { Ago } from "@/components/ago";
import { Empty, Failure, Loading } from "@/components/states";
import { useT } from "@/i18n";
import { KindMark } from "@/lib/brands";
import { kindStyle } from "@/lib/icons";
import { say, why } from "@/lib/messages";
import { cn } from "@/lib/utils";
import { clean, type JournalSearch } from "./search";

/**
 * The latest events about one thing (a connection, a satellite, a person), each opening in the
 * journal, with a link to the whole journal narrowed to it.
 */
export function ActivityList({
  filters,
  search,
  limit = 8,
  empty,
}: {
  filters: JournalFilters;
  search: JournalSearch; // the same filters, as the journal's URL
  limit?: number;
  empty: string;
}) {
  const t = useT();
  const latest = useQuery(journalLatestQuery(filters, limit));
  if (latest.isPending) return <Loading lines={3} />;
  if (latest.isError) return <Failure error={latest.error} retry={() => void latest.refetch()} />;
  if (latest.data.items.length === 0) return <Empty>{empty}</Empty>;
  return (
    <div>
      <ol className="divide-y divide-rule rounded-md border border-rule bg-paper-raised">
        {latest.data.items.map((item) => {
          const style = kindStyle(item.kind);
          const Icon = style.icon;
          return (
            <li key={item.id}>
              <Link
                to="/journal"
                search={clean({ ...search, event: item.id })}
                className="grid grid-cols-[1.25rem_1fr_auto] items-baseline gap-x-3 px-4 py-2.5 hover:bg-paper-sunken/60"
              >
                <Icon className={cn("size-3.5 translate-y-0.5", style.tone)} aria-hidden="true" />
                <span className="min-w-0">
                  <span className={cn("block truncate text-sm", item.tone === "warning" ? "text-brick" : "text-ink")}>
                    {say(item)}
                  </span>
                  {item.reason ? (
                    <span className="block truncate text-sm text-ink-muted">
                      <span className="font-mono text-[0.7rem] text-ember">{t("jr-why")} </span>
                      {why(item)}
                    </span>
                  ) : item.detail ? (
                    <span className="block truncate text-sm text-ink-muted">{item.detail}</span>
                  ) : null}
                </span>
                <span className="flex items-center gap-2 font-mono text-[0.7rem] text-ink-faint">
                  {item.brand ? <KindMark kind={item.brand} className="size-3" /> : null}
                  <Ago iso={item.at} />
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
      <Link
        to="/journal"
        search={clean(search)}
        className="mt-3 inline-flex items-center gap-1 font-mono text-xs text-ink-muted hover:text-ink"
      >
        {t("jr-all-in-journal")} <ArrowRight className="size-3" aria-hidden="true" />
      </Link>
    </div>
  );
}
