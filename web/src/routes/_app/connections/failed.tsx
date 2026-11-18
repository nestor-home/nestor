import { createFileRoute } from "@tanstack/react-router";
import { FailedView } from "@/features/connections/failed-view";

interface Search {
  kind?: string;
  error?: string;
}

/** Where the OAuth callback sends the browser when connecting did not work. */
export const Route = createFileRoute("/_app/connections/failed")({
  validateSearch: (search: Record<string, unknown>): Search => ({
    kind: typeof search.kind === "string" ? search.kind : undefined,
    error: typeof search.error === "string" ? search.error : undefined,
  }),
  component: Failed,
});

function Failed() {
  const { kind, error } = Route.useSearch();
  return <FailedView kind={kind} error={error} />;
}
