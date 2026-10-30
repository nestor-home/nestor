import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Connection, type Connector, type ConnectRequest, keys } from "@/api";

export type ConnectPhase = "idle" | "pending" | "redirecting" | "connected" | "failed";

/**
 * Connecting an account. OAuth answers with the provider's consent page, where the browser goes;
 * the provider then brings it back to `/connections/<id>?connected=1` (or to `/connections/failed`).
 * Other connectors answer with the connection at once.
 */
export function useConnect(
  kind: string,
  auth: Connector["auth"],
  {
    leave = (url: string) => window.location.assign(url),
    onConnected,
  }: { leave?: (url: string) => void; onConnected: (connection: Connection) => void },
) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (request: ConnectRequest) => api.connect(kind, request, auth),
    onSuccess: (result) => {
      if (result.kind === "redirect") {
        leave(result.url);
        return;
      }
      void queryClient.invalidateQueries({ queryKey: keys.connections });
      onConnected(result.connection);
    },
  });
  const phase: ConnectPhase = mutation.isPending
    ? "pending"
    : mutation.isError
      ? "failed"
      : mutation.data?.kind === "redirect"
        ? "redirecting"
        : mutation.isSuccess
          ? "connected"
          : "idle";
  return { phase, connect: mutation.mutate, error: mutation.error };
}
