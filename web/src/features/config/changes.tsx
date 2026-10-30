import { Minus, Pencil, Plus } from "lucide-react";
import type { ConfigChange, ConfigDiff } from "@/api";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";
import { shown } from "./schema";

type Sort = "added" | "removed" | "changed";

const MARK = { added: Plus, removed: Minus, changed: Pencil } as const;

/** What a write would change, line by line: the path, then before → after (never a secret's value). */
export function Changes({ diff, className }: { diff: ConfigDiff; className?: string }) {
  const t = useT();
  const rows: [Sort, ConfigChange][] = [
    ...diff.changed.map((c) => ["changed", c] as [Sort, ConfigChange]),
    ...diff.added.map((c) => ["added", c] as [Sort, ConfigChange]),
    ...diff.removed.map((c) => ["removed", c] as [Sort, ConfigChange]),
  ].sort((a, b) => a[1].path.localeCompare(b[1].path, undefined, { numeric: true }));
  if (!rows.length) return <p className="text-sm text-ink-muted">{t("cfg-no-change")}</p>;
  return (
    <ul className={cn("divide-y divide-rule border-y border-rule", className)}>
      {rows.map(([sort, change]) => {
        const Icon = MARK[sort];
        return (
          <li key={`${sort}:${change.path}`} className="grid grid-cols-[1rem_1fr] gap-x-2 py-2.5">
            <Icon
              className={cn(
                "mt-0.5 size-3.5",
                sort === "added" ? "text-sage" : sort === "removed" ? "text-brick" : "text-ember",
              )}
              aria-label={t(`cfg-change-${sort}`)}
            />
            <div className="min-w-0">
              <p className="font-mono text-[0.78rem] [overflow-wrap:anywhere] text-ink">{change.path}</p>
              <p className="mt-0.5 font-mono text-[0.72rem] [overflow-wrap:anywhere] text-ink-muted">
                {change.secret ? (
                  t("cfg-change-secret")
                ) : sort === "added" ? (
                  shown(change.after)
                ) : sort === "removed" ? (
                  <span className="line-through">{shown(change.before)}</span>
                ) : (
                  <>
                    <span className="line-through decoration-ink-faint">{shown(change.before)}</span>
                    <span className="px-1.5 text-ink-faint" aria-hidden="true">
                      →
                    </span>
                    <span className="sr-only">{t("cfg-change-becomes")}</span>
                    <span className="text-ink">{shown(change.after)}</span>
                  </>
                )}
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
