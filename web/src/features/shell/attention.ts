import { useQuery } from "@tanstack/react-query";
import type { LinkProps } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import {
  CircleAlert,
  Hourglass,
  House,
  KeyRound,
  MessageSquareOff,
  RadioTower,
  ServerCrash,
  ShieldQuestion,
} from "lucide-react";
import {
  type Component,
  confirmationsQuery,
  connectionsQuery,
  homeQuery,
  journalLatestQuery,
  satellitesQuery,
  systemQuery,
  tasksQuery,
} from "@/api";
import { tr } from "@/i18n/runtime";
import { remaining, startOfToday } from "@/lib/dates";
import { is } from "@/lib/events";
import { rendered, say } from "@/lib/messages";
import { useCan } from "@/lib/session";

/** Components that already speak for themselves: connections, tools and satellites. */
const SPEAK_FOR_THEMSELVES = new Set<Component["slot"]>(["satellite", "tools", "connector", "home"]);

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
  const confirmations = useQuery({ ...confirmationsQuery, enabled: useCan("messages:read") });
  const home = useQuery({ ...homeQuery, enabled: useCan("home:read") });

  const items: Attention[] = [];
  for (const c of confirmations.data ?? []) {
    if (!c.yours) continue;
    items.push({
      key: `confirmation-${c.id}`,
      icon: ShieldQuestion,
      tone: "attention",
      title: tr("attention-confirmation", { tool: c.tool }),
      detail: tr("attention-confirmation-detail", { left: remaining(c.expires_at) }),
      action: tr("attention-answer"),
      link: { to: "/messages" },
    });
  }
  if (home.data && home.data.health !== "started") {
    items.push({
      key: "home",
      icon: House,
      tone: home.data.health === "unavailable" ? "error" : "attention",
      title: tr("attention-home", { health: home.data.health }),
      detail: home.data.health_detail ?? "",
      action: tr("action-see"),
      link: { to: "/house" },
    });
  }
  for (const c of connections.data ?? []) {
    if (c.status === "connected") continue;
    items.push({
      key: `connection-${c.id}`,
      icon: c.status === "needs_reauth" ? KeyRound : CircleAlert,
      tone: c.status === "needs_reauth" ? "attention" : "error",
      title: tr(c.status === "needs_reauth" ? "attention-reauth" : "attention-connection-error", {
        account: c.account,
      }),
      detail: rendered(c.status_reason) || tr("attention-tools-hidden"),
      action: tr(c.status === "needs_reauth" ? "attention-reconnect" : "action-see"),
      link: { to: "/connections/$connectionId", params: { connectionId: c.id } },
    });
  }
  for (const p of satellites.data?.pending ?? []) {
    items.push({
      key: `pairing-${p.pairing_id}`,
      icon: Hourglass,
      tone: "attention",
      title: tr("attention-pairing", { device: p.device.id }),
      detail: tr("attention-pairing-detail", { model: p.device.model, room: p.device.room }),
      action: tr("attention-approve"),
      link: { to: "/satellites", search: { approve: p.pairing_id } },
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
      detail: f.detail_text,
      action: tr("attention-understand"),
      link: { to: "/journal", search: { event: f.position } },
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
    if (c.health !== "unavailable" || SPEAK_FOR_THEMSELVES.has(c.slot)) continue;
    items.push({
      key: `component-${c.slot}-${c.name}`,
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
