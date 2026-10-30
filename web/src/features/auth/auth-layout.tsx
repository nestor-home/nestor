import type { ReactNode } from "react";
import { AgentFigure } from "@/components/agent-figure";
import { Wordmark } from "@/components/wordmark";
import { useT } from "@/i18n";

/** The frame of the pages seen before signing in: the form on paper, the signature texture beside it. */
export function AuthLayout({ title, intro, children }: { title: string; intro?: ReactNode; children: ReactNode }) {
  const t = useT();
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
      <div className="grid grid-rows-[auto_1fr_auto] px-6 py-8 md:px-12">
        <header>
          <Wordmark className="text-[1.6rem]" />
        </header>
        <main className="mx-auto flex w-full max-w-sm flex-col justify-center py-16">
          <h1 className="text-[2.6rem] leading-none font-normal">{title}</h1>
          {intro ? <p className="mt-4 text-ink-muted">{intro}</p> : null}
          <div className="mt-8" />
          {children}
        </main>
        <footer className="font-mono text-[0.7rem] text-ink-faint">{t("auth-footer")}</footer>
      </div>
      <div aria-hidden="true" className="relative hidden border-l border-rule bg-paper-sunken lg:block">
        <div className="absolute inset-0 grid place-items-center">
          <AgentFigure state="idle" size="hero" ground live />
        </div>
      </div>
    </div>
  );
}
