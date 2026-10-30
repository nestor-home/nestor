import { Search } from "lucide-react";
import { Kbd } from "@/components/status";
import { useT } from "@/i18n";

/** Along the top of every screen, only the way to jump anywhere (⌘K): the pages carry the rest. */
export function Ticker({ onSearch }: { onSearch: () => void }) {
  const t = useT();
  return (
    <div className="sticky top-0 z-20 hidden h-14 items-center justify-end bg-paper/90 px-4 backdrop-blur-[2px] sm:px-6 md:flex md:px-10 lg:px-14">
      <button
        type="button"
        onClick={onSearch}
        className="inline-flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm text-ink-muted hover:bg-paper-sunken hover:text-ink"
      >
        <Search className="size-4" aria-hidden="true" />
        {t("shell-go-to")}
        <Kbd>⌘K</Kbd>
      </button>
    </div>
  );
}
