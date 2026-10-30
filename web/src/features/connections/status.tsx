import type { ConnectionStatus } from "@/api";
import { Status, type StatusTone } from "@/components/status";
import { connectionStatusLabel } from "@/lib/labels";

const TONE: Record<ConnectionStatus, StatusTone> = { connected: "ok", needs_reauth: "attention", error: "error" };

export function ConnectionStatusMark({ status }: { status: ConnectionStatus }) {
  return <Status tone={TONE[status]}>{connectionStatusLabel(status)}</Status>;
}
