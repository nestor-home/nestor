import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { meQuery } from "@/api";
import { AuthLayout } from "@/features/auth/auth-layout";
import { LoginForm } from "@/features/auth/login-form";
import { useT } from "@/i18n";

/** Only a path of this site: never `//evil.example` or `https://…`. */
export function safeNext(target: unknown): string {
  return typeof target === "string" && target.startsWith("/") && !target.startsWith("//") && !target.includes("\\")
    ? target
    : "/journal";
}

export const Route = createFileRoute("/login")({
  validateSearch: (search: Record<string, unknown>): { next?: string } =>
    typeof search.next === "string" ? { next: search.next } : {},
  beforeLoad: async ({ context, search }) => {
    const me = await context.queryClient.ensureQueryData(meQuery).catch(() => null);
    if (me) throw redirect({ href: safeNext(search.next) });
  },
  component: Login,
});

function Login() {
  const { next } = Route.useSearch();
  const navigate = useNavigate();
  const t = useT();
  return (
    <AuthLayout title={t("auth-login-title")} intro={t("auth-login-intro")}>
      <LoginForm onSignedIn={() => void navigate({ href: safeNext(next), replace: true })} />
    </AuthLayout>
  );
}
