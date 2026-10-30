import { createFileRoute } from "@tanstack/react-router";
import { Empty } from "@/components/states";
import { ConfigPageView } from "@/features/config/config-pages";
import { useConfigEditor } from "@/features/config/editor";
import { pageOf } from "@/features/config/sections";
import { useT } from "@/i18n";

export const Route = createFileRoute("/_app/config/$section")({ component: SectionRoute });

function SectionRoute() {
  const { section } = Route.useParams();
  const t = useT();
  const { schema } = useConfigEditor();
  const page = pageOf(section, schema);
  if (!page || page.kind === "secrets" || page.kind === "history") return <Empty>{t("cfg-unknown-page")}</Empty>;
  return <ConfigPageView key={page.slug} page={page} />;
}
