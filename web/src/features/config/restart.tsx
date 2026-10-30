/**
 * "Restart required": the written configuration applies only once a person restarts the instance.
 * Never automatic — the banner says what is pending, the dialog what a restart does, then it waits
 * for the instance to answer again with nothing pending.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import { ChevronRight, RotateCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ApiError, api, type Me, meQuery, messageOf, setCsrfToken } from "@/api";
import { AgentFigure } from "@/components/agent-figure";
import { Dither } from "@/components/dither";
import { useNotify } from "@/components/notices";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useT } from "@/i18n";
import { useCan, useMe } from "@/lib/session";

/** How often the instance is asked whether it is back, and when waiting is worth saying. */
export const RESTART_POLL_MS = 1_000;
const SLOW_AFTER_MS = 30_000;

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((done, fail) => {
    const timer = setTimeout(done, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      fail(signal.reason);
    });
  });

/**
 * Polls `/health`, then `/me`, until the instance is back with nothing left to apply. Sessions live
 * in the process's memory: a restart signs everyone out, which comes back as `"signed-out"`.
 */
export async function waitForRestart(signal: AbortSignal, onSlow: () => void): Promise<Me | "signed-out"> {
  const started = Date.now();
  let warned = false;
  for (;;) {
    await sleep(RESTART_POLL_MS, signal);
    if (!warned && Date.now() - started > SLOW_AFTER_MS) {
      warned = true;
      onSlow();
    }
    if (!(await api.health(signal))) continue;
    try {
      const me = await api.me(signal);
      if (!me.restart_required) return me;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return "signed-out";
      // up but not ready yet, or the old process still answering: ask again
    }
  }
}

type Phase = "idle" | "restarting" | "slow";

export function RestartBanner() {
  const t = useT();
  const me = useMe();
  const canRestart = useCan("config:manage");
  const queryClient = useQueryClient();
  const notify = useNotify();
  const navigate = useNavigate();
  const here = useRouterState({ select: (s) => s.location.href });
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<unknown>(null);
  const [asking, setAsking] = useState(false);
  const [pending, setPending] = useState(false);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => () => abort.current?.abort(), []);

  const restart = async () => {
    setPending(true);
    setError(null);
    try {
      await api.restart();
    } catch (failure) {
      setError(failure);
      setPending(false);
      return;
    }
    setPending(false);
    setAsking(false);
    setPhase("restarting");
    const controller = new AbortController();
    abort.current = controller;
    try {
      const back = await waitForRestart(controller.signal, () => setPhase("slow"));
      if (back === "signed-out") {
        // the new process knows no session: sign in again, then come back here
        notify(t("cfg-restart-signed-out", { agent: me.agent.name }));
        setCsrfToken(null);
        queryClient.clear();
        void navigate({ to: "/login", search: { next: here } });
        return;
      }
      queryClient.setQueryData(meQuery.queryKey, back);
      setCsrfToken(back.csrf_token);
      await queryClient.invalidateQueries();
      setPhase("idle");
      notify(t("cfg-restart-done", { agent: back.agent.name }));
    } catch {
      // left the page while waiting
    }
  };

  if (phase !== "idle") {
    return (
      <div
        role="status"
        className="relative mb-8 flex items-center gap-3 overflow-hidden rounded-md border border-rule bg-paper-raised px-4 py-3"
      >
        <Dither shape="ramp-right" from={0} to={0.35} className="absolute inset-y-0 right-0 w-1/3 text-ink/40" />
        <AgentFigure state="sleeping" size="md" className="relative" />
        <p className="relative text-sm text-ink">
          {t("cfg-restarting", { agent: me.agent.name })}
          <span className="block text-xs text-ink-muted">
            {phase === "slow" ? t("cfg-restarting-slow") : t("cfg-restarting-hint")}
          </span>
        </p>
      </div>
    );
  }
  if (!me.restart_required) return null;
  const count = me.pending_changes.length;
  return (
    <Collapsible className="relative mb-8 overflow-hidden rounded-md border border-rule bg-paper-raised">
      <Dither
        shape="ramp-right"
        from={0}
        to={0.25}
        className="pointer-events-none absolute top-0 right-0 h-full w-1/4 text-ink/30"
      />
      <div className="relative flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <RotateCw className="size-4 text-ember" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="text-sm text-ink">
            {t("cfg-restart-required")}
            <span className="text-ink-muted"> — {t("cfg-pending", { count })}</span>
          </p>
          {count ? (
            <CollapsibleTrigger className="group/pending mt-0.5 inline-flex items-center gap-1 font-mono text-[0.7rem] text-ink-muted hover:text-ink">
              <ChevronRight
                className="size-3 transition-transform group-data-panel-open/pending:rotate-90"
                aria-hidden="true"
              />
              {t("cfg-pending-show")}
            </CollapsibleTrigger>
          ) : null}
        </div>
        {canRestart ? (
          <AlertDialog
            open={asking}
            onOpenChange={(next) => {
              if (pending) return;
              setAsking(next);
              if (!next) setError(null);
            }}
          >
            <AlertDialogTrigger
              render={
                <Button variant="outline" size="sm">
                  {t("cfg-restart")}
                </Button>
              }
            />
            <AlertDialogContent className="max-w-md! border border-rule bg-paper-raised">
              <AlertDialogHeader>
                <AlertDialogTitle className="font-serif text-xl font-normal">
                  {t("cfg-restart-title", { agent: me.agent.name })}
                </AlertDialogTitle>
                <AlertDialogDescription className="text-ink-muted">
                  {t("cfg-restart-text", { agent: me.agent.name })}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <ul className="grid gap-1.5 text-sm text-ink">
                <li>{t("cfg-restart-channels")}</li>
                <li>{t("cfg-restart-tasks")}</li>
                <li>{t("cfg-restart-apply", { count })}</li>
              </ul>
              {error ? (
                <p role="alert" className="text-sm text-brick">
                  {messageOf(error)}
                </p>
              ) : null}
              <AlertDialogFooter className="bg-paper-sunken/60">
                <AlertDialogCancel disabled={pending}>{t("action-cancel")}</AlertDialogCancel>
                <Button variant="accent" onClick={restart} disabled={pending}>
                  {pending ? "…" : t("cfg-restart-now")}
                </Button>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        ) : (
          <p className="text-xs text-ink-muted">{t("cfg-restart-ask")}</p>
        )}
      </div>
      {count ? (
        <CollapsibleContent>
          <ul className="relative grid gap-0.5 border-t border-dashed border-rule px-4 py-3 pl-12 font-mono text-[0.72rem] text-ink-muted">
            {me.pending_changes.map((path) => (
              <li key={path} className="[overflow-wrap:anywhere]">
                {path}
              </li>
            ))}
          </ul>
        </CollapsibleContent>
      ) : null}
    </Collapsible>
  );
}
