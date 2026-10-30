import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { HomeView } from "@/features/home/home-view";

export const Route = createFileRoute("/_app/")({ component: Home });

function Home() {
  return (
    <Guard scope="journal:read">
      <HomeView />
    </Guard>
  );
}
