/**
 * "Configuration", at a glance: every part of the file as a card saying what is set now, grouped by
 * what a person tunes. What is not saved yet is said first, with the way to save it.
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, FileCog } from "lucide-react";
import { configHistoryQuery, secretsQuery } from "@/api";
import { Crumbs } from "@/components/crumbs";
import { IconTile, Pebble, ServiceTile } from "@/components/marks";
import { PageHeader, Section } from "@/components/page";
import { useT } from "@/i18n";
import { PageMark, SaveBar, usePageMarks } from "./config-layout";
import { useConfigEditor } from "./editor";
import { type ConfigPage, GROUP_LABEL, groupsFor, pageTitle } from "./sections";
import { glanceOf, peopleOf } from "./summary";

const MARKS = 4;

export function ConfigOverview() {
  const t = useT();
  const { schema, state } = useConfigEditor();
  return (
    <div>
      <PageHeader
        title={t("cfg-title")}
        crumbs={
          <Crumbs trail={[{ label: t("space-settings"), link: { to: "/settings" } }, { label: t("cfg-title") }]} />
        }
        meta={
          <>
            <FileCog className="size-3.5 shrink-0" aria-hidden="true" />
            <span className="font-mono text-xs [overflow-wrap:anywhere]">{state.path}</span>
          </>
        }
      >
        {t("cfg-intro")}
      </PageHeader>
      <div className="grid gap-10">
        <SaveBar inline />
        {groupsFor(schema).map(({ group, pages }) => (
          <Section key={group} title={t(GROUP_LABEL[group])}>
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {pages.map((page) => (
                <PageCard key={page.slug} page={page} />
              ))}
            </ul>
          </Section>
        ))}
      </div>
    </div>
  );
}

/** A part of the file: the logos of what it holds (else its tile), its name, and what is set now. */
function PageCard({ page }: { page: ConfigPage }) {
  const t = useT();
  const { schema, draft } = useConfigEditor();
  const marks = usePageMarks()(page);
  const glance = useGlance(page);
  const people = page.kind === "household" ? peopleOf(draft) : [];
  const to = `/config/${page.slug}`;
  return (
    <li>
      <Link to={to} className="surface flex h-full flex-col gap-4 p-5">
        <span className="flex items-center gap-1.5">
          {people.length ? (
            people.slice(0, MARKS).map((p, i) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: a person's position is its place in the file
              <Pebble key={i} name={String(p.name || p.id || "")} className="size-10 text-[1rem]" />
            ))
          ) : glance.marks.length ? (
            glance.marks.slice(0, MARKS).map((mark) => <ServiceTile key={mark} kind={mark} />)
          ) : (
            <IconTile icon={page.icon} />
          )}
          {Math.max(people.length, glance.marks.length) > MARKS ? (
            <span className="pl-1 text-[0.88rem] text-ink-muted tabular">
              {t("cfg-sum-extra", { count: Math.max(people.length, glance.marks.length) - MARKS })}
            </span>
          ) : null}
          <span className="ml-auto flex items-center gap-2.5">
            <PageMark {...marks} />
            <ArrowRight className="size-4 text-ink-faint" aria-hidden="true" />
          </span>
        </span>
        <span>
          <span className="block font-serif text-[1.35rem] leading-tight text-ink">{pageTitle(page, schema, t)}</span>
          <span className="mt-1.5 line-clamp-2 block text-[0.95rem] [overflow-wrap:anywhere] text-ink-muted">
            {glance.line}
          </span>
        </span>
      </Link>
    </li>
  );
}

/** What a page holds now: read from the draft, or from the vault and the history for their own pages. */
function useGlance(page: ConfigPage): { marks: string[]; line: string } {
  const t = useT();
  const { schema, draft } = useConfigEditor();
  const secrets = useQuery({ ...secretsQuery, enabled: page.kind === "secrets" });
  const history = useQuery({ ...configHistoryQuery, enabled: page.kind === "history" });
  if (page.kind === "secrets") {
    const unset = secrets.data?.filter((s) => !s.set).length ?? 0;
    const count = secrets.data?.length;
    if (count === undefined) return { marks: [], line: "" };
    return { marks: [], line: unset ? t("cfg-sum-secrets-unset", { count, unset }) : t("cfg-sum-secrets", { count }) };
  }
  if (page.kind === "history")
    return { marks: [], line: history.data ? t("cfg-sum-history", { count: history.data.length }) : "" };
  return glanceOf(page, schema, draft);
}
