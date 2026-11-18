/** Where the OAuth callback sends the browser when connecting did not work: what went wrong, then the next step. */

import { Link } from "@tanstack/react-router";
import { RotateCw, ShieldX } from "lucide-react";
import { CardHead } from "@/components/card";
import { Crumbs } from "@/components/crumbs";
import { IconTile, ServiceTile } from "@/components/marks";
import { PageHeader, Section } from "@/components/page";
import { buttonVariants } from "@/components/ui/button";
import { useT } from "@/i18n";
import { kindName } from "@/lib/brands";
import { trail } from "./trail";

/** The OAuth errors the callback reports, each with its title, what happened and what to do, in the catalogue. */
const KNOWN: Record<string, { title: string; text?: string; next: string }> = {
  access_denied: { title: "conn-failed-denied", text: "conn-failed-denied-text", next: "conn-failed-denied-next" },
  expired: { title: "conn-failed-expired", text: "conn-failed-expired-text", next: "conn-failed-expired-next" },
  unknown_flow: { title: "conn-failed-unknown", text: "conn-failed-unknown-text", next: "conn-failed-unknown-next" },
  exchange_failed: {
    title: "conn-failed-exchange",
    text: "conn-failed-exchange-text",
    next: "conn-failed-exchange-next",
  },
  forbidden: { title: "conn-failed-forbidden", text: "conn-failed-forbidden-text", next: "conn-failed-forbidden-next" },
  provider_error: { title: "conn-failed-provider", next: "conn-failed-provider-next" },
};

export function FailedView({ kind, error }: { kind: string | undefined; error: string | undefined }) {
  const t = useT();
  const known = error ? KNOWN[error] : undefined;
  return (
    <div>
      <PageHeader
        crumbs={<Crumbs trail={trail(t("conn-failed-crumb"))} />}
        title={known ? t(known.title) : t("conn-failed-other")}
      >
        {known
          ? known.text && t(known.text)
          : t("conn-failed-other-text", { error: error ?? t("conn-failed-no-code") })}
      </PageHeader>
      <div className="grid gap-10">
        <Section title={t("conn-failed-next")}>
          <div className="surface max-w-2xl p-4">
            <CardHead
              mark={kind ? <ServiceTile kind={kind} /> : <IconTile icon={ShieldX} tone="brick" />}
              title={kind ? kindName(kind) : t("conn-failed-other")}
              line={known ? t(known.next) : t("conn-failed-other-next")}
            >
              <span className="flex flex-wrap gap-2">
                {kind ? (
                  <Link to="/connections/catalogue" search={{ connect: kind }} className={buttonVariants()}>
                    <RotateCw aria-hidden="true" /> {t("conn-failed-retry")}
                  </Link>
                ) : null}
                <Link to="/connections" className={buttonVariants({ variant: "outline" })}>
                  {t("conn-failed-back")}
                </Link>
              </span>
            </CardHead>
          </div>
        </Section>
      </div>
    </div>
  );
}
