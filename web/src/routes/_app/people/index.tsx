import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { PageHeader } from "@/components/page";
import { PeopleList } from "@/features/people/people";
import { useT } from "@/i18n";

export const Route = createFileRoute("/_app/people/")({ component: People });

function People() {
  const t = useT();
  return (
    <Guard scope="people:read">
      <PageHeader title={t("people-title")}>{t("people-intro")}</PageHeader>
      <PeopleList />
    </Guard>
  );
}
