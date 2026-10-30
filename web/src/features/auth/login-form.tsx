import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, keys, setCsrfToken } from "@/api";
import { Field } from "@/components/field";
import { FormError } from "@/components/states";
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

  function submit(event: FormEvent) {
    event.preventDefault();
    signIn.mutate({ login, password });
  }

  return (
    <form onSubmit={submit} className="grid gap-5" noValidate={false}>
      <Field label={t("auth-login")} htmlFor="login">
        <Input
          id="login"
          autoComplete="username"
          autoCapitalize="none"
          required
          autoFocus
          spellCheck={false}
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
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>
      <FormError error={signIn.error} />
      <Button type="submit" size="lg" disabled={signIn.isPending}>
        {signIn.isPending ? t("auth-signing-in") : t("auth-sign-in")}
      </Button>
    </form>
  );
}
