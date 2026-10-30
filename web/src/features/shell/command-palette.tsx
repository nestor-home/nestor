import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Moon, Plug, RadioTower, Sun, User } from "lucide-react";
import { useEffect, useState } from "react";
import { connectionsQuery, peopleQuery, satellitesQuery } from "@/api";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@/components/ui/command";
import { useT } from "@/i18n";
import { useCan, useMe } from "@/lib/session";
import { useTheme } from "@/lib/theme";
import { flatNav } from "./nav";

/** ⌘K: jump to a section, a person, a connection or a satellite, or switch the theme. */
export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const t = useT();
  const me = useMe();
  const navigate = useNavigate();
  const { resolved, choose } = useTheme();
  const canConnections = useCan("connections:read");
  const canSatellites = useCan("satellites:read");
  const people = useQuery({ ...peopleQuery, enabled: open });
  const connections = useQuery({ ...connectionsQuery, enabled: open && canConnections });
  const satellites = useQuery({ ...satellitesQuery, enabled: open && canSatellites });
  const go = (action: () => void) => {
    onOpenChange(false);
    action();
  };
  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("shell-go-to")}
      description={t("shell-palette-description")}
    >
      <CommandInput placeholder={t("shell-palette-placeholder")} />
      <CommandList>
        <CommandEmpty>{t("shell-palette-empty")}</CommandEmpty>
        <CommandGroup heading={t("shell-sections")}>
          {flatNav(me.scopes).map((item) => (
            <CommandItem
              key={item.to}
              value={`section ${t(item.label)}`}
              onSelect={() => go(() => void navigate({ to: item.to }))}
            >
              <item.icon aria-hidden="true" />
              {t(item.label)}
              <CommandShortcut>g {item.key}</CommandShortcut>
            </CommandItem>
          ))}
        </CommandGroup>
        {people.data?.length ? (
          <CommandGroup heading={t("nav-people")}>
            {people.data.map((p) => (
              <CommandItem
                key={p.id}
                value={`personne ${p.name}`}
                onSelect={() => go(() => void navigate({ to: "/people/$personId", params: { personId: p.id } }))}
              >
                <User aria-hidden="true" />
                {p.name}
              </CommandItem>
            ))}
          </CommandGroup>
        ) : null}
        {connections.data?.length ? (
          <CommandGroup heading={t("nav-connections")}>
            {connections.data.map((c) => (
              <CommandItem
                key={c.id}
                value={`connexion ${c.account} ${c.title}`}
                onSelect={() =>
                  go(() => void navigate({ to: "/connections/$connectionId", params: { connectionId: c.id } }))
                }
              >
                <Plug aria-hidden="true" />
                {c.account}
              </CommandItem>
            ))}
          </CommandGroup>
        ) : null}
        {satellites.data?.paired.length ? (
          <CommandGroup heading={t("nav-satellites")}>
            {satellites.data.paired.map((s) => (
              <CommandItem
                key={s.id}
                value={`satellite ${s.id} ${s.room}`}
                onSelect={() =>
                  go(() => void navigate({ to: "/satellites/$satelliteId", params: { satelliteId: s.id } }))
                }
              >
                <RadioTower aria-hidden="true" />
                {s.id}
                <CommandShortcut>{s.room}</CommandShortcut>
              </CommandItem>
            ))}
          </CommandGroup>
        ) : null}
        <CommandGroup heading={t("shell-display")}>
          <CommandItem
            value={t("shell-palette-theme-keywords")}
            onSelect={() => go(() => choose(resolved === "dark" ? "light" : "dark"))}
          >
            {resolved === "dark" ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
            {t(resolved === "dark" ? "shell-theme-to-light" : "shell-theme-to-dark")}
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}

export function useCommandKey(setOpen: (update: (open: boolean) => boolean) => void): void {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);
}

export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useCommandKey(setOpen);
  return { open, setOpen };
}
