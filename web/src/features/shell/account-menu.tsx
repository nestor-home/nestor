import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { ChevronsUpDown, Languages, LogOut, Monitor, Moon, Sun } from "lucide-react";
import { api, keys, setCsrfToken } from "@/api";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { isLocale, type Locale, useLocale, useT } from "@/i18n";
import { roleLabel } from "@/lib/labels";
import { useMe } from "@/lib/session";
import { type ThemeChoice, useTheme } from "@/lib/theme";

/** Language names in their own language: whoever does not read the current one finds theirs. */
const LANGUAGES: { value: Locale; name: string }[] = [
  { value: "en", name: "English" },
  { value: "fr", name: "Français" },
];

export function AccountMenu({ compact = false }: { compact?: boolean }) {
  const t = useT();
  const me = useMe();
  const { choice, choose } = useTheme();
  const { locale, setLocale } = useLocale();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const logout = useMutation({
    mutationFn: api.logout,
    onSettled: () => {
      setCsrfToken(null);
      queryClient.clear();
      void navigate({ to: "/login" });
    },
  });
  const language = useMutation({
    mutationFn: (next: Locale) => api.setLocale(next),
    onMutate: (next) => setLocale(next),
    onSuccess: (updated) => {
      queryClient.setQueryData(keys.me, updated);
      // server-rendered texts (journal, reasons, connectors) come back in the new language
      void queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "me" });
    },
  });

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={
          compact
            ? "grid size-11 place-items-center rounded-md hover:bg-paper-sunken data-popup-open:bg-paper-sunken md:size-9"
            : "flex w-full items-center gap-3 rounded-md px-2 py-2 text-left hover:bg-paper-sunken data-popup-open:bg-paper-sunken"
        }
      >
        <span
          aria-hidden="true"
          className="grid size-7 shrink-0 place-items-center rounded-sm bg-ink font-serif text-sm text-paper"
        >
          {(me.account.person_name ?? me.account.login).slice(0, 1).toUpperCase()}
        </span>
        {compact ? null : (
          <>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm text-ink">{me.account.person_name ?? me.account.login}</span>
              <span className="block truncate text-[0.85rem] text-ink-muted">{roleLabel(me.account.role)}</span>
            </span>
            <ChevronsUpDown className="size-4 text-ink-faint" aria-hidden="true" />
          </>
        )}
        <span className="sr-only">{t("shell-account-menu")}</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        side={compact ? "bottom" : "top"}
        align={compact ? "end" : "start"}
        className="w-60 border border-rule bg-paper-raised"
      >
        <DropdownMenuGroup>
          <DropdownMenuLabel className="font-mono text-[0.7rem] font-normal">{me.account.login}</DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuLabel className="label-mono">{t("shell-theme")}</DropdownMenuLabel>
          <DropdownMenuRadioGroup value={choice} onValueChange={(value) => choose(value as ThemeChoice)}>
            <DropdownMenuRadioItem value="system">
              <Monitor /> {t("shell-theme-system")}
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="light">
              <Sun /> {t("shell-theme-light")}
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="dark">
              <Moon /> {t("shell-theme-dark")}
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuLabel className="label-mono flex items-center gap-1.5">
            <Languages className="size-3" aria-hidden="true" /> {t("shell-language")}
          </DropdownMenuLabel>
          <DropdownMenuRadioGroup value={locale} onValueChange={(value) => isLocale(value) && language.mutate(value)}>
            {LANGUAGES.map((l) => (
              <DropdownMenuRadioItem key={l.value} value={l.value} lang={l.value}>
                {l.name}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => logout.mutate()}>
          <LogOut /> {t("shell-sign-out")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
