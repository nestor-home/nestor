import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { ConfigLayout } from "@/features/config/config-layout";

export const Route = createFileRoute("/_app/config")({ component: Config });

function Config() {
  return (
    <Guard scope="config:manage">
      <ConfigLayout />
    </Guard>
  );
}
