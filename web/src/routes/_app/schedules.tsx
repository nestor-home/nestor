import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { PageHeader } from "@/components/page";
import { SchedulesList } from "@/features/schedules/schedules";
import { useT } from "@/i18n";

export const Route = createFileRoute("/_app/schedules")({ component: Page });

function Page() {
  const t = useT();
  return (
    <Guard scope="schedules:read">
      <PageHeader title={t("schedule-title")}>{t("schedule-lede")}</PageHeader>
      <SchedulesList />
    </Guard>
  );
}
