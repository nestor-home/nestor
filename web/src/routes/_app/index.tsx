import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { TodayView } from "@/features/today/today-view";

export const Route = createFileRoute("/_app/")({ component: Home });

function Home() {
  return (
    <Guard scope="journal:read">
      <TodayView />
    </Guard>
  );
}
