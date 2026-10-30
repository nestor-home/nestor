import { createFileRoute, redirect } from "@tanstack/react-router";
import { ApiError, meQuery } from "@/api";
import { AppShell } from "@/features/shell/app-shell";
import { LiveProvider } from "@/features/shell/live";

export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context, location }) => {
    try {
      await context.queryClient.ensureQueryData(meQuery);
    } catch (error) {
      if (error instanceof ApiError && error.unauthenticated) {
        throw redirect({ to: "/login", search: { next: location.href } });
      }
      throw error;
    }
  },
  component: Shell,
});

function Shell() {
  const { stream } = Route.useRouteContext();
  return (
    <LiveProvider stream={stream}>
      <AppShell />
    </LiveProvider>
  );
}
