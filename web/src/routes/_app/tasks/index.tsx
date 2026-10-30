import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { PageHeader } from "@/components/page";
import { TasksList } from "@/features/tasks/tasks";
import { useT } from "@/i18n";

export const Route = createFileRoute("/_app/tasks/")({ component: Tasks });

function Tasks() {
  const t = useT();
  return (
    <Guard scope="tasks:read">
      <PageHeader title={t("task-title")} />
      <TasksList />
    </Guard>
  );
}
