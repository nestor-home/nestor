import { Localized } from "@fluent/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, type InvitationCreated, keys, type Role } from "@/api";
import { Choice } from "@/components/choice";
import { CopyField } from "@/components/copy-field";
import { Field } from "@/components/field";
import { PersonPicker } from "@/components/person-picker";
import { FormError } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { roleHint, roleLabel } from "@/lib/labels";

/** The roles as options, in the active locale (called at render, not at import). */
export function roleOptions(): { value: Role; label: string }[] {
  return (["guest", "member", "admin", "owner"] as Role[]).map((r) => ({ value: r, label: roleLabel(r) }));
}

/** Invite someone: once created, the dialog shows the link to send (it is shown only once). */
export function InviteForm({ onDone }: { onDone: () => void }) {
  const t = useT();
  const queryClient = useQueryClient();
  const [role, setRole] = useState<Role>("member");
  const [person, setPerson] = useState("");
  const [sent, setSent] = useState<InvitationCreated | null>(null);
  const invite = useMutation({
    mutationFn: () => api.invite({ role, person: person || null }),
    onSuccess: (invitation) => {
      setSent(invitation);
      void queryClient.invalidateQueries({ queryKey: keys.invitations });
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    invite.mutate();
  }

  if (sent) {
    return (
      <div role="status" className="grid gap-3">
        <Localized
          id="acc-invite-sent"
          vars={{ person: sent.invitation.person_name ?? "", has_person: sent.invitation.person_name ? "yes" : "no" }}
          elems={{ strong: <strong /> }}
        >
          <p className="text-sm" />
        </Localized>
        <CopyField value={sent.link} label={t("acc-invite-link")} />
        <Button variant="outline" className="justify-self-end" onClick={onDone}>
          {t("acc-invite-done")}
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <Field label={t("acc-person")} htmlFor="invite-person" hint={t("acc-person-hint")}>
        <PersonPicker id="invite-person" value={person} onChange={setPerson} empty={t("acc-person-none")} />
      </Field>
      <Field label={t("acc-role")} htmlFor="invite-role" hint={roleHint(role)}>
        <Choice id="invite-role" value={role} options={roleOptions()} onChange={setRole} />
      </Field>
      <FormError error={invite.error} />
      <Button type="submit" disabled={invite.isPending} className="justify-self-end">
        {invite.isPending ? t("acc-inviting") : t("acc-invite-create")}
      </Button>
    </form>
  );
}
