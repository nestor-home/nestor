/**
 * The Configuration area: one draft of the file for all its pages, the frame every page shares (where
 * it sits, the way to another section), the bar that saves the draft, and the guard on leaving it.
 */
import { Link, Outlet, useBlocker, useNavigate, useRouterState } from "@tanstack/react-router";
import { ChevronsUpDown, FilePenLine, LoaderCircle } from "lucide-react";
import { type ReactNode, useState } from "react";
import { messageOf } from "@/api";
import { Confirm } from "@/components/confirm";
import { Crumbs } from "@/components/crumbs";
import { FormActions } from "@/components/form-actions";
import { IconTile } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { BottomSheet, FormSheet } from "@/components/overlay-form";
import { PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";
import { Changes } from "./changes";
import { ConfigEditorProvider, changeCount, useConfigEditor } from "./editor";
import { changedKeys, problemsUnder } from "./schema";
import { type ConfigPage, GROUP_LABEL, groupsFor, pageOfKey, pageTitle } from "./sections";

export function ConfigLayout() {
  const overview = useRouterState({ select: (s) => s.location.pathname.replace(/\/$/, "") === "/config" });
  return (
    <ConfigEditorProvider>
      <Outlet />
      {/* the overview states the draft at its top; a page keeps it in reach under what is edited */}
      {overview ? null : <SaveBar />}
      <LeaveGuard />
    </ConfigEditorProvider>
  );
}

/** Where a page of the file stands in the draft: its problems, and whether it differs from the file. */
export function usePageMarks() {
  const { base, draft, problems, dirty } = useConfigEditor();
  const changed = dirty ? changedKeys(base, draft) : new Set<string>();
  return (page: ConfigPage) => ({
    problems: page.keys.reduce((n, k) => n + problemsUnder(problems, [k]).length, 0),
    changed: page.keys.some((k) => changed.has(k)),
  });
}

/**
 * A page of the configuration: its trail back to the settings, its title and what it tunes, then its
 * sections. The other sections are a list beside it on a wide screen, a drawer on a narrow one.
 */
export function ConfigFrame({
  title,
  about,
  actions,
  children,
}: {
  title: string;
  about?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const t = useT();
  return (
    <div>
      <PageHeader
        title={title}
        crumbs={
          <Crumbs
            trail={[
              { label: t("space-settings"), link: { to: "/settings" } },
              { label: t("cfg-title"), link: { to: "/config" } },
              { label: title },
            ]}
          />
        }
        actions={
          <>
            {actions}
            <SectionSwitch />
          </>
        }
      >
        {about}
      </PageHeader>
      <div className="grid gap-10 lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-12">
        <aside className="hidden lg:block">
          <div className="sticky top-8">
            <SectionNav />
          </div>
        </aside>
        <div className="grid min-w-0 content-start gap-10">{children}</div>
      </div>
    </div>
  );
}

/** Every page of the configuration by group, the current one marked, with what the draft changed or broke. */
function SectionNav({ onGo }: { onGo?: () => void }) {
  const t = useT();
  const { schema } = useConfigEditor();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const marks = usePageMarks();
  return (
    <nav aria-label={t("cfg-nav")} className="grid gap-5">
      {groupsFor(schema).map(({ group, pages }) => (
        <div key={group}>
          <p className="caption mb-1.5 px-2.5 text-ink-muted">{t(GROUP_LABEL[group])}</p>
          <ul className="grid gap-0.5">
            {pages.map((page) => {
              const to = `/config/${page.slug}`;
              const here = path === to;
              const mark = marks(page);
              return (
                <li key={page.slug}>
                  <Link
                    to={to}
                    onClick={onGo}
                    aria-current={here ? "page" : undefined}
                    className={cn(
                      "flex min-h-9 items-center gap-2.5 rounded-lg px-2.5 text-[0.95rem] text-ink-muted hover:bg-paper-sunken hover:text-ink",
                      here && "bg-paper-sunken font-medium text-ink",
                    )}
                  >
                    <page.icon className={cn("size-4", here ? "text-ember" : "text-ink-faint")} aria-hidden="true" />
                    <span className="min-w-0 flex-1 truncate">{pageTitle(page, schema, t)}</span>
                    <PageMark {...mark} />
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

/** What the draft did to a page, beside its name: the problems it has, else that it changed. */
export function PageMark({ problems, changed }: { problems: number; changed: boolean }) {
  const t = useT();
  if (problems)
    return (
      <span className="rounded-full bg-brick-soft px-1.5 text-[0.8rem] font-medium text-brick tabular">
        {problems}
        <span className="sr-only"> {t("cfg-problems", { count: problems })}</span>
      </span>
    );
  if (changed)
    return (
      <span className="size-2 rounded-full bg-ember">
        <span className="sr-only">{t("cfg-modified")}</span>
      </span>
    );
  return null;
}

/** On a narrow screen, the way to another section: a drawer from the bottom, not a list that eats the page. */
function SectionSwitch() {
  const t = useT();
  const [open, setOpen] = useState(false);
  return (
    <BottomSheet
      open={open}
      onOpenChange={setOpen}
      title={t("cfg-title")}
      trigger={
        <Button variant="outline" size="sm" className="lg:hidden">
          <ChevronsUpDown /> {t("cfg-switch")}
        </Button>
      }
    >
      <div className="px-3 py-4">
        <SectionNav onGo={() => setOpen(false)} />
      </div>
    </BottomSheet>
  );
}

/**
 * The one place a draft is written: how many changes, what is wrong with them, cancel and save. It floats
 * under the page being edited; `inline`, it is the first thing the overview says.
 */
export function SaveBar({ inline = false }: { inline?: boolean }) {
  const t = useT();
  const editor = useConfigEditor();
  const notify = useNotify();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  if (!editor.dirty && !editor.saving) return null;
  const count = changeCount(editor.diff);
  const problems = editor.problems.length;
  const first = editor.problems[0];
  const goToProblem = () => {
    const page = first ? pageOfKey(String(first.path[0] ?? ""), editor.schema) : undefined;
    if (page) void navigate({ to: "/config/$section", params: { section: page.slug } });
  };
  const save = async () => {
    if (await editor.save()) {
      setOpen(false);
      notify(t("cfg-saved"));
    }
  };
  const blocked = editor.saving || editor.checking || problems > 0;
  return (
    <section
      aria-label={t("cfg-save-region")}
      className={cn(
        "surface flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3",
        inline ? "" : "sticky bottom-[calc(5rem+env(safe-area-inset-bottom))] z-20 mt-10 md:bottom-5",
      )}
    >
      <IconTile icon={FilePenLine} tone={problems ? "brick" : "ember"} />
      <div className="grid min-w-0 flex-1 gap-0.5">
        <p className="font-medium text-ink">{t("cfg-save-region")}</p>
        <p aria-live="polite" className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.9rem]">
          {editor.checking ? (
            <span className="inline-flex items-center gap-1.5 text-ink-muted">
              <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
              {t("cfg-checking")}
            </span>
          ) : null}
          {problems ? (
            <button type="button" onClick={goToProblem} className="text-brick underline underline-offset-4">
              {t("cfg-problems", { count: problems })}
            </button>
          ) : null}
          {/* a problem with no field to show it at: said here */}
          {editor.problems
            .filter((p) => !p.path.length)
            .map((p) => (
              <span key={p.message} className="text-brick">
                {p.message}
              </span>
            ))}
          {count ? (
            <button type="button" onClick={() => setOpen(true)} className="text-ink underline underline-offset-4">
              {t("cfg-changes", { count })}
            </button>
          ) : null}
          {editor.saveError && !problems ? <span className="text-brick">{messageOf(editor.saveError)}</span> : null}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Confirm
          trigger={
            <Button variant="ghost" disabled={editor.saving}>
              {t("cfg-discard")}
            </Button>
          }
          title={t("cfg-discard-title")}
          confirm={t("cfg-discard-confirm")}
          onConfirm={async () => editor.discard()}
        >
          {t("cfg-discard-text")}
        </Confirm>
        <Button variant="accent" onClick={save} disabled={blocked || count === 0}>
          {editor.saving ? t("cfg-saving") : t("cfg-save")}
        </Button>
      </div>
      <FormSheet open={open} onOpenChange={setOpen} title={t("cfg-changes-title")} description={t("cfg-changes-text")}>
        {(close) => (
          <div className="grid gap-6 pt-5">
            {editor.diff ? <Changes diff={editor.diff} /> : null}
            <FormActions>
              <Button variant="outline" onClick={close}>
                {t("action-close")}
              </Button>
              <Button variant="accent" onClick={save} disabled={blocked}>
                {editor.saving ? t("cfg-saving") : t("cfg-save")}
              </Button>
            </FormActions>
          </div>
        )}
      </FormSheet>
    </section>
  );
}

/** Leaving the area drops the draft: said before it happens. */
function LeaveGuard() {
  const t = useT();
  const { dirty } = useConfigEditor();
  const blocker = useBlocker({
    shouldBlockFn: ({ next }) => dirty && !next.pathname.startsWith("/config"),
    enableBeforeUnload: dirty,
    withResolver: true,
  });
  return (
    <Confirm
      open={blocker.status === "blocked"}
      onOpenChange={(open) => !open && blocker.reset?.()}
      title={t("cfg-leave-title")}
      confirm={t("cfg-leave-go")}
      cancel={t("cfg-leave-stay")}
      onConfirm={async () => blocker.proceed?.()}
    >
      {t("cfg-leave-text")}
    </Confirm>
  );
}
