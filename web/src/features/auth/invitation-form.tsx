import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, type InvitationPreview, keys, setCsrfToken } from "@/api";
import { Field } from "@/components/field";
import { FormError } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useT } from "@/i18n";

export const MIN_PASSWORD = 12;

export function InvitationForm({
  token,
  invitation,
  onAccepted,
}: {
  token: string;
  invitation: InvitationPreview;
  onAccepted: () => void;
}) {
  const t = useT();
  const queryClient = useQueryClient();
  const [login, setLogin] = useState(
    (invitation.person_name ?? "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[^a-z0-9]/g, ""),
  );
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const accept = useMutation({
    mutationFn: () => api.acceptInvitation(token, { login: login.trim(), password }),
    onSuccess: (me) => {
      setCsrfToken(me.csrf_token);
      queryClient.setQueryData(keys.me, me);
      onAccepted();
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (password.length < MIN_PASSWORD) return setProblem(t("auth-password-too-short", { min: MIN_PASSWORD }));
    if (password !== repeat) return setProblem(t("auth-password-mismatch"));
    setProblem(null);
    accept.mutate();
  }

  return (
    <form onSubmit={submit} className="grid gap-5">
      <Field label={t("auth-login")} htmlFor="login" hint={t("auth-login-hint")}>
        <Input
          id="login"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          required
          className="font-mono"
          value={login}
          onChange={(e) => setLogin(e.target.value)}
        />
      </Field>
      <Field label={t("auth-password")} htmlFor="password" hint={t("auth-password-hint", { min: MIN_PASSWORD })}>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>
      <Field label={t("auth-password-repeat")} htmlFor="repeat" error={problem}>
        <Input
          id="repeat"
          type="password"
          autoComplete="new-password"
          required
          aria-invalid={problem ? true : undefined}
          value={repeat}
          onChange={(e) => setRepeat(e.target.value)}
        />
      </Field>
      <FormError error={accept.error} />
      <Button type="submit" size="lg" disabled={accept.isPending}>
        {accept.isPending ? t("auth-accepting") : t("auth-accept")}
      </Button>
    </form>
  );
}
