import { createFileRoute, Link } from "@tanstack/react-router";
import { Crumbs } from "@/components/crumbs";
import { PageHeader } from "@/components/page";
import { buttonVariants } from "@/components/ui/button";
import { useT } from "@/i18n";

interface Search {
  kind?: string;
  error?: string;
}

/** The OAuth errors the callback reports, each with its title and explanation in the catalogue. */
const KNOWN: Record<string, { title: string; text: string }> = {
  access_denied: { title: "conn-failed-denied", text: "conn-failed-denied-text" },
  expired: { title: "conn-failed-expired", text: "conn-failed-expired-text" },
  unknown_flow: { title: "conn-failed-unknown", text: "conn-failed-unknown-text" },
  exchange_failed: { title: "conn-failed-exchange", text: "conn-failed-exchange-text" },
};

/** Where the OAuth callback sends the browser when connecting did not work. */
export const Route = createFileRoute("/_app/connections/failed")({
  validateSearch: (search: Record<string, unknown>): Search => ({
    kind: typeof search.kind === "string" ? search.kind : undefined,
    error: typeof search.error === "string" ? search.error : undefined,
  }),
  component: Failed,
});

function Failed() {
  const { kind, error } = Route.useSearch();
  const known = error ? KNOWN[error] : undefined;
  const t = useT();
  return (
    <>
      <PageHeader
        crumbs={
          <Crumbs
            trail={[{ label: t("conn-title"), link: { to: "/connections" } }, { label: t("conn-failed-crumb") }]}
          />
        }
        title={known ? t(known.title) : t("conn-failed-other")}
      >
        {known ? t(known.text) : t("conn-failed-other-text", { error: error ?? t("conn-failed-no-code") })}
      </PageHeader>
      <div className="flex gap-2">
        {kind ? (
          <Link to="/connections/catalogue" search={{ connect: kind }} className={buttonVariants()}>
            {t("conn-failed-retry")}
          </Link>
        ) : null}
        <Link to="/connections" className={buttonVariants({ variant: "outline" })}>
          {t("conn-failed-back")}
        </Link>
      </div>
    </>
  );
}
