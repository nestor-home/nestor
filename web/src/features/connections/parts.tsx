/** What every place that shows a connected account shares: its state and its card. */
import { Link } from "@tanstack/react-router";
import type { Connection, ConnectionStatus } from "@/api";
import { Ago } from "@/components/ago";
import { TILE_CARD, TileCard } from "@/components/card";
import { OwnerMark, ServiceTile } from "@/components/marks";
import { Status, type StatusTone } from "@/components/status";
import { useT } from "@/i18n";
import { connectionStatusLabel } from "@/lib/labels";
import { personName } from "@/lib/people";

const TONE: Record<ConnectionStatus, StatusTone> = { connected: "ok", needs_reauth: "attention", error: "error" };

export function ConnectionStatusMark({ status }: { status: ConnectionStatus }) {
  return <Status tone={TONE[status]}>{connectionStatusLabel(status)}</Status>;
}

/** An account the agent can no longer use until someone reconnects it. */
export const needsSomeone = (connection: Pick<Connection, "status">) => connection.status !== "connected";

/** A connected account in a grid: its service, whose it is, its state and when the agent last used it. */
export function ConnectionCard({ connection: c }: { connection: Connection }) {
  const t = useT();
  return (
    <li>
      <Link to="/connections/$connectionId" params={{ connectionId: c.id }} className={TILE_CARD}>
        <TileCard
          marks={<ServiceTile kind={c.brand ?? c.kind} />}
          aside={<OwnerMark owner={c.owner} />}
          title={c.account}
          line={`${c.title} · ${personName(c.owner)}`}
          foot={
            <>
              <ConnectionStatusMark status={c.status} />
              {c.last_used_at ? (
                <span>
                  {t("conn-last-used")} <Ago iso={c.last_used_at} />
                </span>
              ) : (
                <span>{t("conn-never-used-short")}</span>
              )}
            </>
          }
        />
      </Link>
    </li>
  );
}
