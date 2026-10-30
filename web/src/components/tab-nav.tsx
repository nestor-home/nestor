import { Link, useRouterState } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export interface TabLink {
  to: string; // a full path: the URL decides the tab
  label: string;
  icon?: LucideIcon;
  count?: number;
}

/**
 * shadcn Tabs whose triggers are links: the URL holds the tab, so it is shareable and
 * Back/Forward work; arrow keys move between tabs as in any tab list.
 */
export function TabNav({ tabs, label }: { tabs: TabLink[]; label: string }) {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const active = [...tabs]
    .sort((a, b) => b.to.length - a.to.length)
    .find((t) => path === t.to || path.startsWith(`${t.to}/`));
  return (
    <Tabs value={active?.to ?? tabs[0]?.to} className="mb-8">
      <TabsList
        variant="line"
        aria-label={label}
        className="h-auto w-full justify-start gap-5 overflow-x-auto overflow-y-hidden border-b border-rule pb-0 [scrollbar-width:none]"
      >
        {tabs.map((t) => (
          <TabsTrigger
            key={t.to}
            value={t.to}
            render={<Link to={t.to} />}
            nativeButton={false}
            className="flex-none rounded-none px-0 pb-2.5 text-ink-muted data-active:text-ink group-data-horizontal/tabs:after:bottom-[-1px] after:bg-ember"
          >
            {t.icon ? <t.icon aria-hidden="true" /> : null}
            {t.label}
            {t.count !== undefined ? (
              <span className="font-mono text-[0.7rem] text-ink-faint tabular">{t.count}</span>
            ) : null}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
