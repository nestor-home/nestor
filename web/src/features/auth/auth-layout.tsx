import type { ReactNode } from "react";
import { AgentFigure } from "@/components/agent-figure";
import { Dither } from "@/components/dither";
import { Wordmark } from "@/components/wordmark";
import { orbOf, phaseOf } from "@/features/today/sky";
import { useNow } from "@/hooks/use-now";
import { useT } from "@/i18n";

/** How the agent greets at this hour, as an argument of its lines. */
export function partOfDay(now: Date): "night" | "day" | "evening" {
  const h = now.getHours();
  return h < 5 ? "night" : h < 18 ? "day" : "evening";
}

/**
 * The frame of the pages seen before signing in: the sky of the hour with the agent standing in it and
 * saying its `line`, then the form on paper (beside it on a wide screen).
 */
export function AuthLayout({
  title,
  intro,
  line,
  children,
}: {
  title: string;
  intro?: ReactNode;
  line: string; // what the agent says, in the first person
  children: ReactNode;
}) {
  const t = useT();
  const now = useNow(60_000);
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <div className="p-3 pb-0 lg:pr-0 lg:pb-3">
        <section
          className="sky flex h-full min-h-[19rem] flex-col justify-between"
          data-phase={phaseOf(now)}
          aria-label={t("auth-scene")}
        >
          <Dither
            shape="ramp-down"
            from={0.42}
            to={0}
            dot={3}
            className="absolute inset-0 -z-10 text-(--sky-grain) opacity-35"
          />
          <span aria-hidden="true" className="sky-orb" style={orbOf(now)} />
          <div className="px-5 pt-5 sm:px-8 sm:pt-7">
            <Wordmark className="text-sheet" />
          </div>
          <div>
            <div className="flex items-end gap-3 px-5 sm:px-8">
              <AgentFigure state="idle" size="lg" live ground className="shrink-0" />
              <p className="mb-9 max-w-[20rem] rounded-2xl rounded-bl-sm bg-paper-raised px-4 py-3 text-lead leading-snug text-ink shadow-lg">
                {line}
              </p>
            </div>
            <p className="sky-ground px-5 py-4 text-body sm:px-8">{t("auth-footer")}</p>
          </div>
        </section>
      </div>
      <main className="mx-auto flex w-full max-w-md flex-col justify-center px-5 py-8 sm:px-8 lg:py-16">
        <h1 className="display-2 text-ink">{title}</h1>
        {intro ? <p className="mt-3 text-lead text-ink-muted">{intro}</p> : null}
        <div className="surface mt-7 p-5 sm:p-6">{children}</div>
      </main>
    </div>
  );
}
