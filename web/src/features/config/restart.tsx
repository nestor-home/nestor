/**
 * "Restart required": the written configuration applies only once a person restarts the instance.
 * Never automatic — the banner says what is pending, the dialog what a restart does, then it waits
 * for the instance to answer again with nothing pending.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate, useRouter } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ApiError, api, type Me, meQuery, setCsrfToken } from "@/api";
import { AgentFigure } from "@/components/agent-figure";
import { ConfirmFrame } from "@/components/confirm";
import { useNotify } from "@/components/notices";
import { FormError } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useT } from "@/i18n";
import { useCan, useMe } from "@/lib/session";
import { cn } from "@/lib/utils";

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

export type RestartPhase = "idle" | "restarting" | "slow";

/**
 * A restart, as the restart banner and the update dialog follow it: `restart` asks for one then waits
 * for the instance to answer again; `waitBack` only waits (a release being installed restarts Nestor
 * by itself). Both resolve once it is back, or once the person was signed out.
 */
export function useRestart() {
  const t = useT();
  const me = useMe();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const navigate = useNavigate();
  const router = useRouter();
  const [phase, setPhase] = useState<RestartPhase>("idle");
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => () => abort.current?.abort(), []);

  const waitBack = async () => {
    const controller = new AbortController();
    abort.current = controller;
    setPhase("restarting");
    try {
      const back = await waitForRestart(controller.signal, () => setPhase("slow"));
      if (back === "signed-out") {
        // the new process knows no session: sign in again, then come back here
        notify(t("cfg-restart-signed-out", { agent: me.agent.name }));
        setCsrfToken(null);
        queryClient.clear();
        void navigate({ to: "/login", search: { next: router.state.location.href } });
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

  const restart = async () => {
    setPending(true);
    setError(null);
    try {
      await api.restart();
    } catch (failure) {
      setError(failure);
      return;
    } finally {
      setPending(false);
    }
    await waitBack();
  };

  return { phase, pending, error, clearError: () => setError(null), restart, waitBack };
}

/** While the instance restarts: the agent asleep, and how long it may take. */
export function Restarting({ phase, className }: { phase: RestartPhase; className?: string }) {
  const t = useT();
  const me = useMe();
  return (
    <div role="status" className={cn("flex items-center gap-4 rounded-lg bg-paper-sunken/70 px-5 py-4", className)}>
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

export function RestartBanner() {
  const t = useT();
  const me = useMe();
  const canRestart = useCan("config:manage");
  const { phase, pending, error, clearError, restart } = useRestart();
  const [asking, setAsking] = useState(false);

  if (phase !== "idle") return <Restarting phase={phase} className="mb-10" />;
  if (!me.restart_required) return null;
  const count = me.pending_changes.length;
  return (
    <Collapsible className="mb-10 rounded-lg bg-paper-sunken/70">
      <div className="relative flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <AgentFigure state="concerned" size="sm" />
        <div className="min-w-0 flex-1">
          <p className="text-sm text-ink">
            {t("cfg-restart-required")}
            <span className="text-ink-muted"> · {t("cfg-pending", { count })}</span>
          </p>
          {count ? (
            <CollapsibleTrigger className="group/pending mt-0.5 inline-flex items-center gap-1 text-[0.82rem] text-ink-muted hover:text-ink">
              <ChevronRight
                className="size-3 transition-transform group-data-panel-open/pending:rotate-90"
                aria-hidden="true"
              />
              {t("cfg-pending-show")}
            </CollapsibleTrigger>
          ) : null}
        </div>
        {canRestart ? (
          <ConfirmFrame
            open={asking}
            onOpenChange={(next) => {
              if (pending) return;
              setAsking(next);
              if (!next) clearError();
            }}
            trigger={
              <Button variant="outline" size="sm">
                {t("cfg-restart")}
              </Button>
            }
            title={t("cfg-restart-title", { agent: me.agent.name })}
            description={t("cfg-restart-text", { agent: me.agent.name })}
            details={
              <>
                <ul className="grid gap-1.5 text-sm text-ink">
                  <li>{t("cfg-restart-channels")}</li>
                  <li>{t("cfg-restart-tasks")}</li>
                  <li>{t("cfg-restart-apply", { count })}</li>
                </ul>
                <FormError error={error} />
              </>
            }
            busy={pending}
            action={
              <Button variant="accent" onClick={() => void restart()} disabled={pending}>
                {pending ? "…" : t("cfg-restart-now")}
              </Button>
            }
          />
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
