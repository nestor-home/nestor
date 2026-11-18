/** "Settings": what the installation is made of, for who looks after it. Each card says where it stands. */
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import { ArrowRight, KeyRound, Plug, RadioTower, Server, SlidersHorizontal } from "lucide-react";
import { accountsQuery, connectionsQuery, satellitesQuery, systemQuery } from "@/api";
import { IconTile } from "@/components/marks";
import { PageHeader } from "@/components/page";
import { UpdateAvailable } from "@/features/system/updates";
import { useT } from "@/i18n";
import { type Permission, useCan, useMe } from "@/lib/session";

type To = "/connections" | "/satellites" | "/accounts" | "/config" | "/system";

export function SettingsView() {
  const t = useT();
  const me = useMe();
  const connections = useQuery({ ...connectionsQuery, enabled: useCan("connections:read") });
  const satellites = useQuery({ ...satellitesQuery, enabled: useCan("satellites:read") });
  const accounts = useQuery({ ...accountsQuery, enabled: useCan("accounts:read") });
  const system = useQuery({ ...systemQuery, enabled: useCan("system:read") });
  const offline = satellites.data?.paired.filter((s) => s.connected === false).length ?? 0;
  const cards: { to: To; scope: Permission; icon: LucideIcon; title: string; text: string; state?: string }[] = [
    {
      to: "/connections",
      scope: "connections:read",
      icon: Plug,
      title: t("nav-connections"),
      text: t("set-connections"),
      state: connections.data ? t("set-connections-count", { count: connections.data.length }) : undefined,
    },
    {
      to: "/satellites",
      scope: "satellites:read",
      icon: RadioTower,
      title: t("nav-satellites"),
      text: t("set-satellites"),
      state: satellites.data
        ? offline
          ? t("set-satellites-offline", { count: satellites.data.paired.length, offline })
          : t("set-satellites-count", { count: satellites.data.paired.length })
        : undefined,
    },
    {
      to: "/accounts",
      scope: "accounts:read",
      icon: KeyRound,
      title: t("nav-accounts"),
      text: t("set-accounts"),
      state: accounts.data ? t("set-accounts-count", { count: accounts.data.length }) : undefined,
    },
    {
      to: "/config",
      scope: "config:manage",
      icon: SlidersHorizontal,
      title: t("nav-config"),
      text: t("set-config", { assistant: me.assistant }),
    },
    {
      to: "/system",
      scope: "system:read",
      icon: Server,
      title: t("nav-system"),
      text: t("set-system"),
      state: system.data ? t("shell-version", { version: system.data.nestor.version }) : undefined,
    },
  ];
  return (
    <div>
      <PageHeader title={t("space-settings")}>{t("set-lede", { assistant: me.assistant })}</PageHeader>
      <div className="mb-3 empty:hidden">
        <UpdateAvailable compact={false} />
      </div>
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map((c) => (
          <Card key={c.to} {...c} />
        ))}
      </ul>
    </div>
  );
}

function Card({
  to,
  scope,
  icon,
  title,
  text,
  state,
}: {
  to: To;
  scope: Permission;
  icon: LucideIcon;
  title: string;
  text: string;
  state?: string;
}) {
  if (!useCan(scope)) return null;
  return (
    <li>
      <Link to={to} className="surface flex h-full flex-col gap-4 p-5">
        <span className="flex items-center justify-between">
          <IconTile icon={icon} className="size-11" />
          <ArrowRight className="size-4 text-ink-faint" aria-hidden="true" />
        </span>
        <span>
          <span className="block font-serif text-[1.35rem] leading-tight text-ink">{title}</span>
          <span className="mt-1.5 block text-[0.95rem] text-ink-muted">{text}</span>
        </span>
        {state ? <span className="mt-auto text-[0.88rem] font-medium text-ink">{state}</span> : null}
      </Link>
    </li>
  );
}
