import { useQuery } from "@tanstack/react-query";
import type { LinkProps } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import { CircleAlert, Hourglass, KeyRound, MessageSquareOff, RadioTower, ServerCrash } from "lucide-react";
import { connectionsQuery, journalLatestQuery, satellitesQuery, systemQuery, tasksQuery } from "@/api";
import { tr } from "@/i18n/runtime";
import { startOfToday } from "@/lib/dates";
import { is } from "@/lib/events";
import { say } from "@/lib/messages";
import { useCan } from "@/lib/session";

export interface Attention {
  key: string;
  icon: LucideIcon;
  tone: "attention" | "error";
  title: string; // a sentence: what is wrong
  detail: string; // why it matters or what to do
  action: string; // the verb of the link
  link: LinkProps;
  at?: string;
}

/**
 * What needs a person, gathered from the resources the account may see: a connection to
 * reauthorise, a device waiting to pair, a message that did not arrive, a failed task, a part of
 * the system that is down. Each comes with what to do about it.
 */
export function useAttention(): { items: Attention[]; ready: boolean } {
  const canConnections = useCan("connections:read");
  const canSatellites = useCan("satellites:read");
  const canTasks = useCan("tasks:read");
  const connections = useQuery({ ...connectionsQuery, enabled: canConnections });
  const satellites = useQuery({ ...satellitesQuery, enabled: canSatellites });
  const tasks = useQuery({ ...tasksQuery, enabled: canTasks });
  const system = useQuery({ ...systemQuery, enabled: canSatellites });
  const spoken = useQuery(journalLatestQuery({ kinds: ["delivery"], from: startOfToday() }, 100));

  const items: Attention[] = [];
  for (const c of connections.data ?? []) {
    if (c.status === "connected") continue;
    items.push({
      key: `connection-${c.id}`,
      icon: c.status === "needs_reauth" ? KeyRound : CircleAlert,
      tone: c.status === "needs_reauth" ? "attention" : "error",
      title: tr(c.status === "needs_reauth" ? "attention-reauth" : "attention-connection-error", {
        account: c.account,
      }),
      detail: c.status_reason ?? tr("attention-tools-hidden"),
      action: tr(c.status === "needs_reauth" ? "attention-reconnect" : "action-see"),
      link: { to: "/connections/$connectionId", params: { connectionId: c.id } },
    });
  }
  for (const p of satellites.data?.pending ?? []) {
    items.push({
      key: `pairing-${p.id}`,
      icon: Hourglass,
      tone: "attention",
      title: tr("attention-pairing", { device: p.device.id }),
      detail: tr("attention-pairing-detail", { model: p.device.model, room: p.device.room }),
      action: tr("attention-approve"),
      link: { to: "/satellites", search: { approve: p.id } },
    });
  }
  for (const s of satellites.data?.paired ?? []) {
    if (s.connected !== false) continue;
    items.push({
      key: `satellite-${s.id}`,
      icon: RadioTower,
      tone: "attention",
      title: tr("attention-satellite-offline", { device: s.id }),
      detail: tr("attention-satellite-offline-detail", { room: s.room }),
      action: tr("action-see"),
      link: { to: "/satellites/$satelliteId", params: { satelliteId: s.id } },
    });
  }
  // a message that did not arrive, unless another way delivered it afterwards
  const today = spoken.data?.items ?? [];
  const recovered = new Set<string>();
  for (const f of today) {
    if (!is(f, "deliveryFailed") || !f.links.delivery || recovered.has(f.links.delivery)) continue;
    recovered.add(f.links.delivery);
    if (today.some((d) => is(d, "delivered") && d.links.delivery === f.links.delivery && d.at >= f.at)) continue;
    items.push({
      key: `delivery-${f.id}`,
      icon: MessageSquareOff,
      tone: "error",
      title: say(f),
      detail: f.detail,
      action: tr("attention-understand"),
      link: { to: "/journal", search: { event: f.id } },
      at: f.at,
    });
  }
  const yesterday = new Date(Date.now() - 24 * 3600_000).toISOString();
  for (const task of tasks.data?.recent ?? []) {
    if (task.status !== "failed" || (task.ended_at ?? "") < yesterday) continue;
    items.push({
      key: `task-${task.id}`,
      icon: CircleAlert,
      tone: "error",
      title: tr("attention-task-failed", { objective: task.objective }),
      detail: task.error ?? "",
      action: tr("action-see"),
      link: { to: "/tasks/$taskId", params: { taskId: task.id } },
    });
  }
  for (const c of system.data?.components ?? []) {
    // connections, tools and satellites already speak for themselves above
    if (c.health !== "down" || ["satellite", "tools", "connector"].includes(c.slot)) continue;
    items.push({
      key: `component-${c.id}`,
      icon: ServerCrash,
      tone: "error",
      title: tr("attention-component-down", { name: c.name }),
      detail: c.health_detail ?? "",
      action: tr("action-see"),
      link: { to: "/system" },
    });
  }
  return { items, ready: !connections.isPending || !canConnections };
}
