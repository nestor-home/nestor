import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/config/")({
  beforeLoad: () => {
    throw redirect({ to: "/config/$section", params: { section: "persona" }, replace: true });
  },
});
