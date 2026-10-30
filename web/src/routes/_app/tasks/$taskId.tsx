import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { TaskDetail } from "@/features/tasks/tasks";

export const Route = createFileRoute("/_app/tasks/$taskId")({ component: Page });

function Page() {
  const { taskId } = Route.useParams();
  return (
    <Guard scope="tasks:read">
      <TaskDetail id={taskId} />
    </Guard>
  );
}
