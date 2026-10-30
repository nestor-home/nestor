import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { type FormEvent, useState } from "react";
import { type MemoryQuery, memoriesQuery } from "@/api";
import { PersonPicker } from "@/components/person-picker";
import { Empty, Failure, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { useT } from "@/i18n";
import { useCan } from "@/lib/session";
import { MemoryCard } from "./memory-card";

export function MemoryList({ query }: { query: MemoryQuery }) {
  const t = useT();
  const memories = useQuery(memoriesQuery(query));
  const editable = useCan("memories:write");
  if (memories.isPending) return <Loading lines={4} />;
  if (memories.isError) return <Failure error={memories.error} retry={() => void memories.refetch()} />;
  if (memories.data.length === 0) {
    return (
      <Empty hint={query.q ? undefined : t("mem-empty-hint")}>{query.q ? t("mem-empty-search") : t("mem-empty")}</Empty>
    );
  }
  return (
    <ul className="grid gap-3 md:grid-cols-2">
      {memories.data.map((m) => (
        <MemoryCard key={`${m.id}-${m.updated_at}`} memory={m} editable={editable} />
      ))}
    </ul>
  );
}

export function MemoriesView({ query, onQuery }: { query: MemoryQuery; onQuery: (next: MemoryQuery) => void }) {
  const t = useT();
  const [q, setQ] = useState(query.q ?? "");
  function submit(event: FormEvent) {
    event.preventDefault();
    onQuery({ ...query, q: q.trim() || undefined });
  }
  return (
    <>
      <search className="mb-8">
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <div className="grid gap-1">
            <label htmlFor="memory-search" className="text-[0.8rem] font-medium">
              {t("mem-search")}
            </label>
            <InputGroup className="w-72">
              <InputGroupAddon>
                <Search aria-hidden="true" />
              </InputGroupAddon>
              <InputGroupInput
                id="memory-search"
                type="search"
                placeholder={t("mem-search-placeholder")}
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </InputGroup>
          </div>
          <div className="grid gap-1">
            <label htmlFor="memory-about" className="text-[0.8rem] font-medium">
              {t("mem-about")}
            </label>
            <PersonPicker
              id="memory-about"
              value={query.about ?? ""}
              onChange={(about) => onQuery({ ...query, about: about || undefined })}
              empty={t("mem-about-everyone")}
              className="w-52"
            />
          </div>
          <Button type="submit" variant="outline">
            {t("mem-search-submit")}
          </Button>
        </form>
      </search>
      <MemoryList query={query} />
    </>
  );
}
