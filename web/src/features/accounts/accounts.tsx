import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { MailPlus } from "lucide-react";
import {
  type Account,
  type AccountChange,
  accountQuery,
  accountsQuery,
  api,
  type Invitation,
  invitationsQuery,
  isMissing,
  keys,
  type Role,
} from "@/api";
import { Ago } from "@/components/ago";
import { Choice } from "@/components/choice";
import { Confirm } from "@/components/confirm";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { IconTile, Pebble } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { FormDialog } from "@/components/overlay-form";
import { Fact, Facts, PageHeader, RowList, Section } from "@/components/page";
import { Empty, Failure, FormError, Loading } from "@/components/states";
import { Status, Tag } from "@/components/status";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { moment } from "@/lib/dates";
import { roleHint, roleLabel } from "@/lib/labels";
import { useCan, useMe } from "@/lib/session";
import { InviteForm, roleOptions } from "./invite-form";
import { isLastOwner } from "./rules";

const nameOf = (account: Account) => account.person?.name ?? account.login;

/**
 * "Accounts": who may open the admin and what their role allows, each one a card that leads to their account;
 * inviting is a dialog, and the invitations still waiting sit below, where one invites.
 */
export function AccountsView() {
  const t = useT();
  const canWrite = useCan("accounts:write");
  const accounts = useQuery(accountsQuery);
  const trail: Crumb[] = [{ label: t("space-settings"), link: { to: "/settings" } }, { label: t("acc-title") }];
  return (
    <>
      <PageHeader
        crumbs={<Crumbs trail={trail} />}
        title={t("acc-title")}
        actions={
          canWrite ? (
            <FormDialog
              trigger={
                <Button>
                  <MailPlus aria-hidden="true" /> {t("acc-invite")}
                </Button>
              }
              title={t("acc-invite-title")}
              description={t("acc-invite-description")}
            >
              {(close) => <InviteForm onDone={close} />}
            </FormDialog>
          ) : null
        }
      >
        {t("acc-intro")}
      </PageHeader>
      <div className="grid gap-10">
        <Section title={t("acc-people")} count={accounts.data?.length}>
          {accounts.isPending ? (
            <Loading lines={3} />
          ) : accounts.isError ? (
            <Failure error={accounts.error} retry={() => void accounts.refetch()} />
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {accounts.data.map((a) => (
                <AccountCard key={a.id} account={a} />
              ))}
            </ul>
          )}
        </Section>
        {canWrite ? <Invitations /> : null}
      </div>
    </>
  );
}

/** Someone who may sign in: who they are, their role and what it allows. */
function AccountCard({ account }: { account: Account }) {
  const t = useT();
  const me = useMe();
  return (
    <li>
      <Link
        to="/accounts/$accountId"
        params={{ accountId: account.id }}
        className="surface flex h-full flex-col gap-4 p-5"
      >
        <span className="flex items-start justify-between gap-3">
          <Pebble name={nameOf(account)} away={account.disabled} size="xl" />
          <span className="flex flex-wrap justify-end gap-2 pt-1">
            {account.id === me.account.id ? <Tag tone="accent">{t("acc-you")}</Tag> : null}
            {account.disabled ? <Status tone="idle">{t("acc-disabled")}</Status> : null}
          </span>
        </span>
        <span className="min-w-0">
          <span className="block title-card [overflow-wrap:anywhere] text-ink">{nameOf(account)}</span>
          <span className="mt-1 block truncate text-body text-ink-muted">{account.login}</span>
        </span>
        <span className="mt-auto border-t border-rule pt-3">
          <span className="block text-body font-medium text-ink first-letter:uppercase">{roleLabel(account.role)}</span>
          <span className="block text-meta text-ink-muted">{roleHint(account.role)}</span>
        </span>
      </Link>
    </li>
  );
}

/** The invitations nobody accepted yet: who for, with which role, until when, and a way to withdraw each. */
function Invitations() {
  const t = useT();
  const invitations = useQuery(invitationsQuery);
  return (
    <Section title={t("acc-invitations")} count={invitations.data?.length}>
      {invitations.isPending ? (
        <Loading lines={1} />
      ) : invitations.isError ? (
        <Failure error={invitations.error} retry={() => void invitations.refetch()} />
      ) : invitations.data.length === 0 ? (
        <Empty hint={t("acc-invitations-empty-hint")}>{t("acc-invitations-empty")}</Empty>
      ) : (
        <RowList>
          {invitations.data.map((i) => (
            <InvitationRow key={i.id} invitation={i} />
          ))}
        </RowList>
      )}
    </Section>
  );
}

function InvitationRow({ invitation }: { invitation: Invitation }) {
  const t = useT();
  const queryClient = useQueryClient();
  const revoke = useMutation({
    mutationFn: () => api.revokeInvitation(invitation.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.invitations }),
  });
  const who = invitation.person?.name ?? t("acc-invitation-anyone");
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-3 px-5 py-4">
      <IconTile icon={MailPlus} tone="amber" />
      <div className="min-w-0 flex-1 basis-48">
        <p className="font-medium text-ink">{who}</p>
        <p className="text-meta text-ink-muted">
          {t("acc-invitation-line", { role: roleLabel(invitation.role), expires: moment(invitation.expires_at) })}
        </p>
      </div>
      <Confirm
        trigger={
          <Button variant="ghost" size="sm">
            {t("acc-revoke")}
          </Button>
        }
        title={t("acc-revoke-title")}
        confirm={t("acc-revoke-confirm")}
        onConfirm={() => revoke.mutateAsync()}
      >
        {t("acc-revoke-text", { has_person: invitation.person ? "yes" : "no", person: invitation.person?.name ?? "" })}
      </Confirm>
    </li>
  );
}

function useChange(account: Account) {
  const me = useMe();
  const queryClient = useQueryClient();
  const notify = useNotify();
  return useMutation({
    mutationFn: (body: AccountChange) => api.changeAccount(account.id, body),
    onSuccess: (updated, body) => {
      queryClient.setQueryData<Account[]>(keys.accounts, (all) => all?.map((a) => (a.id === updated.id ? updated : a)));
      queryClient.setQueryData(keys.account(updated.id), updated);
      if (body.role) notify(tr("acc-role-changed", { name: nameOf(updated), role: roleLabel(updated.role) }));
      else notify(tr(updated.disabled ? "acc-disabled-done" : "acc-enabled-done", { name: nameOf(updated) }));
      if (updated.id === me.account.id) void queryClient.invalidateQueries({ queryKey: keys.me });
    },
  });
}

/** One account: who it is, its role and what the role allows, and whether it may still sign in. */
export function AccountDetail({ id }: { id: string }) {
  const t = useT();
  const found = useQuery(accountQuery(id));
  const accounts = useQuery(accountsQuery); // whether this is the last owner
  const me = useMe();
  const editable = useCan("accounts:write");
  const account = found.data;
  const trail: Crumb[] = [
    { label: t("space-settings"), link: { to: "/settings" } },
    { label: t("acc-title"), link: { to: "/accounts" } },
    { label: account?.login ?? id },
  ];
  const change = useChange(account ?? ({ id } as Account));
  if (found.isPending) return <Loading lines={3} />;
  if (!account) {
    return (
      <>
        <Crumbs trail={trail} />
        {isMissing(found.error) ? <Empty>{t("acc-not-found")}</Empty> : <Failure error={found.error} />}
      </>
    );
  }
  const lastOwner = isLastOwner(account, accounts.data ?? []);
  return (
    <>
      <PageHeader
        crumbs={<Crumbs trail={trail} />}
        title={
          <span className="flex items-center gap-4">
            <Pebble name={nameOf(account)} away={account.disabled} size="2xl" />
            <span className="min-w-0">{nameOf(account)}</span>
          </span>
        }
        meta={
          <>
            {account.disabled ? (
              <Status tone="idle">{t("acc-disabled")}</Status>
            ) : (
              <Status tone="ok">{t("acc-active")}</Status>
            )}
            <span>{account.login}</span>
            {account.id === me.account.id ? <Tag tone="accent">{t("acc-you")}</Tag> : null}
          </>
        }
      />
      <div className="grid max-w-2xl gap-10">
        <Facts className="surface max-w-none p-5">
          <Fact term={t("acc-field-person")}>
            {account.person ? (
              <Link to="/people/$personId" params={{ personId: account.person.id }} className="hover:text-ember">
                {account.person.name}
              </Link>
            ) : (
              <span className="text-ink-muted">{t("acc-person-none-lower")}</span>
            )}
          </Fact>
          <Fact term={t("acc-field-created")}>{moment(account.created_at)}</Fact>
          <Fact term={t("acc-field-seen")}>
            {account.last_seen_at ? (
              <Ago iso={account.last_seen_at} />
            ) : (
              <span className="text-ink-muted">{t("acc-never")}</span>
            )}
          </Fact>
        </Facts>
        <Section title={t("acc-role")}>
          <div className="surface grid gap-3 p-5">
            {editable ? (
              <div className="max-w-sm">
                <label htmlFor="account-role" className="sr-only">
                  {t("acc-role")}
                </label>
                <Choice
                  id="account-role"
                  value={account.role}
                  options={roleOptions()}
                  disabled={lastOwner || account.disabled || change.isPending}
                  describedBy="account-role-allows"
                  onChange={(role: Role) => change.mutate({ role })}
                />
              </div>
            ) : (
              <p className="font-medium text-ink first-letter:uppercase">{roleLabel(account.role)}</p>
            )}
            <p id="account-role-allows" className="text-body text-ink-muted">
              {roleHint(account.role)}
            </p>
            {lastOwner && editable ? <p className="text-body text-amber">{t("acc-last-owner")}</p> : null}
            <FormError error={change.error} />
          </div>
        </Section>
        {editable ? (
          <Section title={t("acc-signin")}>
            <div className="surface flex flex-wrap items-center justify-between gap-x-6 gap-y-4 p-5">
              <p className="max-w-md text-body text-ink-muted">
                {account.disabled ? t("acc-disabled-note") : lastOwner ? t("acc-last-owner") : t("acc-disable-hint")}
              </p>
              {account.disabled ? (
                <Button
                  variant="outline"
                  onClick={() => change.mutate({ disabled: false })}
                  disabled={change.isPending}
                >
                  {t("acc-enable")}
                </Button>
              ) : (
                <Confirm
                  trigger={
                    <Button variant="destructive" disabled={lastOwner}>
                      {t("acc-disable")}
                    </Button>
                  }
                  title={t("acc-disable-title", { name: nameOf(account) })}
                  confirm={t("acc-disable-confirm")}
                  onConfirm={() => change.mutateAsync({ disabled: true })}
                >
                  {t("acc-disable-text")}
                </Confirm>
              )}
            </div>
          </Section>
        ) : null}
      </div>
    </>
  );
}
