import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, keys, messageOf, setCsrfToken } from "@/api";
import { ApiError } from "@/api/client";
import { Field } from "@/components/field";
import { Notice } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useT } from "@/i18n";

export function LoginForm({ onSignedIn }: { onSignedIn: () => void }) {
  const t = useT();
  const queryClient = useQueryClient();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const signIn = useMutation({
    mutationFn: api.login,
    onSuccess: (me) => {
      setCsrfToken(me.csrf_token);
      queryClient.setQueryData(keys.me, me);
      onSignedIn();
    },
  });
  const refused = signIn.error instanceof ApiError && signIn.error.code === "invalid_credentials";

  function submit(event: FormEvent) {
    event.preventDefault();
    signIn.mutate({ login, password });
  }

  return (
    <form onSubmit={submit} className="grid gap-5">
      <Field label={t("auth-login")} htmlFor="login">
        <Input
          id="login"
          autoComplete="username"
          autoCapitalize="none"
          required
          autoFocus
          spellCheck={false}
          className="h-11"
          aria-invalid={refused || undefined}
          value={login}
          onChange={(e) => setLogin(e.target.value)}
        />
      </Field>
      <Field label={t("auth-password")} htmlFor="password">
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          className="h-11"
          aria-invalid={refused || undefined}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>
      {signIn.error ? (
        <Notice>
          <p className="font-medium">{messageOf(signIn.error)}</p>
          {refused ? <p className="mt-1 text-ink-muted">{t("auth-login-help")}</p> : null}
        </Notice>
      ) : null}
      <Button type="submit" size="lg" className="h-11" disabled={signIn.isPending}>
        {signIn.isPending ? t("auth-signing-in") : t("auth-sign-in")}
      </Button>
    </form>
  );
}
