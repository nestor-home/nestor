import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { type JournalFilters, journalLatestQuery } from "@/api";
import { Ago } from "@/components/ago";
import { IconTile } from "@/components/marks";
import { RowList } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { useT } from "@/i18n";
import { KindMark } from "@/lib/brands";
import { say, why } from "@/lib/messages";
import { clean, type JournalSearch } from "./search";
import { tileOf } from "./tile";

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
      <RowList ordered>
        {latest.data.items.map((item) => {
          return (
            <li key={item.id}>
              <Link
                to="/journal"
                search={clean({ ...search, event: item.position })}
                className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3.5 px-4 py-3 hover:bg-paper-sunken/60"
              >
                <IconTile {...tileOf(item)} className="size-9" />
                <span className="min-w-0">
                  <span className="block truncate text-[0.98rem] text-ink">{say(item)}</span>
                  {item.reason ? (
                    <span className="block truncate text-[0.88rem] text-ink-muted">
                      <span className="text-ember">{t("jr-why-label")} </span>
                      {why(item)}
                    </span>
                  ) : item.detail_text ? (
                    <span className="block truncate text-[0.88rem] text-ink-muted">{item.detail_text}</span>
                  ) : null}
                </span>
                <span className="flex items-center gap-2 text-[0.85rem] text-ink-muted">
                  {item.brand ? <KindMark kind={item.brand} className="size-3.5" /> : null}
                  <Ago iso={item.at} />
                </span>
              </Link>
            </li>
          );
        })}
      </RowList>
      <Link
        to="/journal"
        search={clean(search)}
        className="mt-3 inline-flex items-center gap-1 text-[0.92rem] text-ink-muted hover:text-ink"
      >
        {t("jr-all-in-journal")} <ArrowRight className="size-3.5" aria-hidden="true" />
      </Link>
    </div>
  );
}
