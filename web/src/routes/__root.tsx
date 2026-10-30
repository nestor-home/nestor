import { createRootRouteWithContext, Link, Outlet } from "@tanstack/react-router";
import { buttonVariants } from "@/components/ui/button";
import { Wordmark } from "@/components/wordmark";
import { useT } from "@/i18n";
import type { RouterContext } from "@/router";

export const Route = createRootRouteWithContext<RouterContext>()({
  component: Outlet,
  notFoundComponent: NotFound,
});

function NotFound() {
  const t = useT();
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center px-6">
      <Wordmark className="mb-12 text-2xl" />
      <h1 className="text-3xl">{t("not-found-title")}</h1>
      <p className="mt-3 text-ink-muted">{t("not-found-text")}</p>
      <Link to="/" className={buttonVariants({ variant: "outline", className: "mt-8 self-start" })}>
        {t("not-found-back")}
      </Link>
    </main>
  );
}
