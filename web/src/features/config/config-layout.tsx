import { Link, Outlet, useBlocker, useNavigate, useRouterState } from "@tanstack/react-router";
import { FileCog, LoaderCircle } from "lucide-react";
import { useState } from "react";
import { messageOf } from "@/api";
import { Confirm } from "@/components/confirm";
import { useNotify } from "@/components/notices";
import { PageHeader } from "@/components/page";
import { TabNav } from "@/components/tab-nav";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useIsMobile } from "@/hooks/use-mobile";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";
import { Changes } from "./changes";
import { ConfigEditorProvider, changeCount, useConfigEditor } from "./editor";
import { changedKeys, problemsUnder } from "./schema";
import { GROUP_LABEL, pageOfKey, pagesFor, pageTitle } from "./sections";

/** The Configuration area: its sub-navigation, the page, and the bar that saves the one draft. */
export function ConfigLayout() {
  return (
    <ConfigEditorProvider>
      <Frame />
    </ConfigEditorProvider>
  );
}

function Frame() {
  const t = useT();
  const { state } = useConfigEditor();
  return (
    <>
      <PageHeader
        title={t("cfg-title")}
        meta={
          <p className="flex min-w-0 items-center gap-1.5 font-mono text-xs text-ink-muted">
            <FileCog className="size-3.5 shrink-0" aria-hidden="true" />
            <span className="[overflow-wrap:anywhere]">{state.path}</span>
          </p>
        }
      >
        {t("cfg-intro")}
      </PageHeader>
      <div className="md:hidden">
        <MobileNav />
      </div>
      <div className="grid gap-10 md:grid-cols-[11.5rem_minmax(0,1fr)] lg:gap-14">
        <aside className="hidden md:block">
          <SubNav />
        </aside>
        <div className="min-w-0">
          <Outlet />
        </div>
      </div>
      <SaveBar />
      <LeaveGuard />
    </>
  );
}

function usePageMarks() {
  const { base, draft, problems, dirty } = useConfigEditor();
  const changed = dirty ? changedKeys(base, draft) : new Set<string>();
  return (keys: string[]) => ({
    problems: keys.reduce((n, k) => n + problemsUnder(problems, [k]).length, 0),
    changed: keys.some((k) => changed.has(k)),
  });
}

function SubNav() {
  const t = useT();
  const { schema } = useConfigEditor();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const marks = usePageMarks();
  const pages = pagesFor(schema);
  const groups = [...new Set(pages.map((p) => p.group))];
  return (
    <nav aria-label={t("cfg-nav")} className="sticky top-6 grid gap-5">
      {groups.map((group) => (
        <div key={group}>
          <p className="label-mono mb-1.5 px-2 text-[0.66rem]">{t(GROUP_LABEL[group])}</p>
          <ul className="grid gap-px">
            {pages
              .filter((p) => p.group === group)
              .map((page) => {
                const to = `/config/${page.slug}`;
                const here = path === to;
                const mark = marks(page.keys);
                return (
                  <li key={page.slug}>
                    <Link
                      to={to}
                      aria-current={here ? "page" : undefined}
                      className={cn(
                        "flex h-8 items-center gap-2 rounded-md px-2 text-[0.85rem] text-ink-muted hover:bg-paper-sunken hover:text-ink",
                        here && "bg-paper-sunken text-ink",
                      )}
                    >
                      <page.icon
                        className={cn("size-3.5", here ? "text-ember" : "text-ink-faint")}
                        aria-hidden="true"
                      />
                      <span className="min-w-0 flex-1 truncate">{pageTitle(page, schema, t)}</span>
                      {mark.problems ? (
                        <span className="font-mono text-[0.68rem] text-brick tabular">
                          {mark.problems}
                          <span className="sr-only"> {t("cfg-problems", { count: mark.problems })}</span>
                        </span>
                      ) : mark.changed ? (
                        <span className="size-1.5 rounded-full bg-ember" title={t("cfg-modified")}>
                          <span className="sr-only">{t("cfg-modified")}</span>
                        </span>
                      ) : null}
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

function MobileNav() {
  const t = useT();
  const { schema } = useConfigEditor();
  return (
    <TabNav
      label={t("cfg-nav")}
      tabs={pagesFor(schema).map((page) => ({
        to: `/config/${page.slug}`,
        label: pageTitle(page, schema, t),
        icon: page.icon,
      }))}
    />
  );
}

/** The one place a draft is written: its state, the changes, cancel and save. */
function SaveBar() {
  const t = useT();
  const editor = useConfigEditor();
  const notify = useNotify();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const mobile = useIsMobile();
  if (!editor.dirty && !editor.saving) return null;
  const count = changeCount(editor.diff);
  const problems = editor.problems.length;
  const first = editor.problems[0];
  const goToProblem = () => {
    const page = first ? pageOfKey(String(first.path[0] ?? ""), editor.schema) : undefined;
    if (page) void navigate({ to: `/config/${page.slug}` });
  };
  const save = async () => {
    if (await editor.save()) {
      setOpen(false);
      notify(t("cfg-saved"));
    }
  };
  return (
    <section
      aria-label={t("cfg-save-region")}
      className="sticky bottom-[env(safe-area-inset-bottom)] z-20 -mx-4 mt-10 border-t border-rule bg-paper/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6 md:-mx-10 md:px-10 lg:-mx-14 lg:px-14"
    >
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2">
        <p aria-live="polite" className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs">
          {editor.checking ? (
            <span className="inline-flex items-center gap-1.5 text-ink-muted">
              <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
              {t("cfg-checking")}
            </span>
          ) : null}
          {problems ? (
            <button type="button" onClick={goToProblem} className="text-brick underline-offset-4 hover:underline">
              {t("cfg-problems", { count: problems })}
            </button>
          ) : null}
          {count ? (
            <button type="button" onClick={() => setOpen(true)} className="text-ink underline-offset-4 hover:underline">
              {t("cfg-changes", { count })}
            </button>
          ) : null}
          {editor.saveError && !problems ? <span className="text-brick">{messageOf(editor.saveError)}</span> : null}
        </p>
        <div className="flex items-center gap-2">
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
          <Button
            variant="accent"
            onClick={save}
            disabled={editor.saving || editor.checking || problems > 0 || count === 0}
          >
            {editor.saving ? t("cfg-saving") : t("cfg-save")}
          </Button>
        </div>
      </div>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent
          side={mobile ? "bottom" : "right"}
          className={cn("w-full overflow-y-auto bg-paper", mobile ? "h-[90dvh]" : "sm:max-w-xl")}
        >
          <SheetHeader className="border-b border-rule px-6 pt-6 pb-4">
            <SheetTitle className="font-serif text-2xl font-normal">{t("cfg-changes-title")}</SheetTitle>
            <SheetDescription>{t("cfg-changes-text")}</SheetDescription>
          </SheetHeader>
          <div className="grid gap-6 px-6 pb-8">
            {editor.diff ? <Changes diff={editor.diff} /> : null}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setOpen(false)}>
                {t("action-close")}
              </Button>
              <Button variant="accent" onClick={save} disabled={editor.saving || editor.checking || problems > 0}>
                {editor.saving ? t("cfg-saving") : t("cfg-save")}
              </Button>
            </div>
          </div>
        </SheetContent>
      </Sheet>
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
    <AlertDialog open={blocker.status === "blocked"} onOpenChange={(open) => !open && blocker.reset?.()}>
      <AlertDialogContent className="max-w-md! border border-rule bg-paper-raised">
        <AlertDialogHeader>
          <AlertDialogTitle className="font-serif text-xl font-normal">{t("cfg-leave-title")}</AlertDialogTitle>
          <AlertDialogDescription className="text-ink-muted">{t("cfg-leave-text")}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="bg-paper-sunken/60">
          <AlertDialogCancel>{t("cfg-leave-stay")}</AlertDialogCancel>
          <Button variant="destructive" onClick={() => blocker.proceed?.()}>
            {t("cfg-leave-go")}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
