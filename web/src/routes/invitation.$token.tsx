import { Localized } from "@fluent/react";
import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { api } from "@/api";
import { Failure, Loading } from "@/components/states";
import { buttonVariants } from "@/components/ui/button";
import { AuthLayout, partOfDay } from "@/features/auth/auth-layout";
import { InvitationForm } from "@/features/auth/invitation-form";
import { useT } from "@/i18n";
import { roleLabel } from "@/lib/labels";

export const Route = createFileRoute("/invitation/$token")({ component: Invitation });

function Invitation() {
  const { token } = Route.useParams();
  const navigate = useNavigate();
  const t = useT();
  const invitation = useQuery({ queryKey: ["invitation", token], queryFn: () => api.invitation(token), retry: false });

  if (invitation.isPending) {
    return (
      <AuthLayout title={t("auth-invitation-title")} line={t("auth-line-checking")}>
        <Loading lines={2} />
      </AuthLayout>
    );
  }
  if (invitation.isError) {
    return (
      <AuthLayout title={t("auth-invitation-title")} intro={t("auth-invitation-invalid")} line={t("auth-line-invalid")}>
        <Failure error={invitation.error} />
        <Link to="/login" className={buttonVariants({ variant: "outline", className: "mt-5" })}>
          {t("auth-go-to-login")}
        </Link>
      </AuthLayout>
    );
  }
  const preview = invitation.data;
  return (
    <AuthLayout
      title={t("auth-welcome")}
      line={t("auth-line-invitation", { part: partOfDay(new Date()) })}
      intro={
        <Localized
          id="auth-invitation-intro"
          vars={{
            role: roleLabel(preview.role),
            person: preview.person?.name ?? "",
            has_person: preview.person?.name ? "yes" : "no",
          }}
          elems={{ strong: <strong className="text-ink" /> }}
        >
          <span />
        </Localized>
      }
    >
      <InvitationForm token={token} invitation={preview} onAccepted={() => void navigate({ to: "/", replace: true })} />
    </AuthLayout>
  );
}
