import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, MailPlus, Users } from "lucide-react";
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
import { Choice } from "@/components/choice";
import { Confirm } from "@/components/confirm";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { useNotify } from "@/components/notices";
import { FormDialog } from "@/components/overlay-form";
import { PageHeader, Section } from "@/components/page";
import { Empty, Failure, FormError, Loading } from "@/components/states";
import { Status, Tag } from "@/components/status";
import { TabNav } from "@/components/tab-nav";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { moment } from "@/lib/dates";
import { roleHint, roleLabel } from "@/lib/labels";
import { usePeopleNames } from "@/lib/people";
import { useCan, useMe } from "@/lib/session";
import { InviteForm, roleOptions } from "./invite-form";
import { isLastOwner } from "./rules";

const lastOwnerText = () => tr("acc-last-owner");

export function AccountsHeader() {
  const t = useT();
  const canWrite = useCan("accounts:write");
  const invitations = useQuery({ ...invitationsQuery, enabled: canWrite });
  const accounts = useQuery(accountsQuery);
  return (
    <>
      <PageHeader
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
      <TabNav
        label={t("acc-title")}
        tabs={[
          { to: "/accounts", label: t("acc-tab-accounts"), icon: Users, count: accounts.data?.length },
          ...(canWrite
            ? [
                {
                  to: "/accounts/invitations",
                  label: t("acc-tab-invitations"),
                  icon: MailPlus,
                  count: invitations.data?.length,
                },
              ]
            : []),
        ]}
      />
    </>
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
      if (body.role)
        notify(tr("acc-role-changed", { name: updated.person_name ?? updated.login, role: roleLabel(updated.role) }));
      else
        notify(
          tr(updated.disabled ? "acc-disabled-done" : "acc-enabled-done", {
            name: updated.person_name ?? updated.login,
          }),
        );
      if (updated.id === me.account.id) void queryClient.invalidateQueries({ queryKey: keys.me });
    },
  });
}

export function AccountsList() {
  const accounts = useQuery(accountsQuery);
  if (accounts.isPending) return <Loading lines={3} />;
  if (accounts.isError) return <Failure error={accounts.error} retry={() => void accounts.refetch()} />;
  return (
    <ul className="divide-y divide-rule rounded-md border border-rule bg-paper-raised">
      {accounts.data.map((a) => (
        <AccountRow key={a.id} account={a} accounts={accounts.data} />
      ))}
    </ul>
  );
}

function AccountRow({ account, accounts }: { account: Account; accounts: Account[] }) {
  const t = useT();
  const me = useMe();
  const editable = useCan("accounts:write");
  const lastOwner = isLastOwner(account, accounts);
  const change = useChange(account);
  const roleId = `role-${account.id}`;
  return (
    <li className="grid gap-x-6 gap-y-2 px-5 py-3.5 sm:grid-cols-[minmax(0,1fr)_11rem_1rem] sm:items-center">
      <Link to="/accounts/$accountId" params={{ accountId: account.id }} className="group min-w-0">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-ink group-hover:text-ember">{account.person_name ?? account.login}</span>
          {account.id === me.account.id ? <Tag tone="accent">{t("acc-you")}</Tag> : null}
          {account.disabled ? <Status tone="idle">{t("acc-disabled")}</Status> : null}
        </span>
        <span className="block truncate font-mono text-[0.7rem] text-ink-muted">
          {account.login} · {roleLabel(account.role)}
        </span>
      </Link>
      <div>
        <label htmlFor={roleId} className="sr-only">
          {t("acc-role-of", { name: account.person_name ?? account.login })}
        </label>
        {editable ? (
          <Choice
            id={roleId}
            size="sm"
            value={account.role}
            options={roleOptions()}
            disabled={lastOwner || account.disabled || change.isPending}
            describedBy={lastOwner ? `${account.id}-last-owner` : undefined}
            onChange={(role: Role) => change.mutate({ role })}
          />
        ) : (
          <Tag>{roleLabel(account.role)}</Tag>
        )}
      </div>
      <ArrowRight className="hidden size-3.5 text-ink-faint sm:block" aria-hidden="true" />
      {lastOwner && editable ? (
        <p id={`${account.id}-last-owner`} className="font-mono text-[0.7rem] text-amber sm:col-span-3">
          {lastOwnerText()}
        </p>
      ) : null}
      {change.error ? (
        <div className="sm:col-span-3">
          <FormError error={change.error} />
        </div>
      ) : null}
    </li>
  );
}

export function InvitationsList() {
  const t = useT();
  const invitations = useQuery(invitationsQuery);
  if (invitations.isPending) return <Loading lines={1} />;
  if (invitations.isError) return <Failure error={invitations.error} retry={() => void invitations.refetch()} />;
  if (invitations.data.length === 0) return <Empty>{t("acc-invitations-empty")}</Empty>;
  return (
    <ul className="divide-y divide-rule rounded-md border border-rule bg-paper-raised">
      {invitations.data.map((i) => (
        <InvitationRow key={i.id} invitation={i} />
      ))}
    </ul>
  );
}

function InvitationRow({ invitation }: { invitation: Invitation }) {
  const t = useT();
  const name = usePeopleNames();
  const queryClient = useQueryClient();
  const revoke = useMutation({
    mutationFn: () => api.revokeInvitation(invitation.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.invitations }),
  });
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5">
      <div>
        <p className="text-sm">{invitation.person_name ?? roleLabel(invitation.role)}</p>
        <p className="font-mono text-[0.7rem] text-ink-muted">
          {t("acc-invitation-pending", {
            role: roleLabel(invitation.role),
            person: invitation.person ? name(invitation.person) : "",
            has_person: invitation.person ? "yes" : "no",
            expires: moment(invitation.expires_at),
          })}
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
        {t("acc-revoke-text", { email: invitation.person_name ?? roleLabel(invitation.role) })}
      </Confirm>
    </li>
  );
}

export function AccountDetail({ id }: { id: string }) {
  const t = useT();
  const found = useQuery(accountQuery(id));
  const accounts = useQuery(accountsQuery); // whether this is the last owner
  const me = useMe();
  const name = usePeopleNames();
  const editable = useCan("accounts:write");
  const account = found.data;
  const trail: Crumb[] = [{ label: t("acc-title"), link: { to: "/accounts" } }, { label: account?.login ?? id }];
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
        title={account.person_name ?? account.login}
        meta={
          <p className="flex flex-wrap items-center gap-x-3 font-mono text-xs text-ink-muted">
            <span>{account.login}</span>
            {account.disabled ? (
              <Status tone="idle">{t("acc-disabled")}</Status>
            ) : (
              <Status tone="ok">{t("acc-active")}</Status>
            )}
            {account.id === me.account.id ? <Tag tone="accent">{t("acc-you")}</Tag> : null}
          </p>
        }
      />
      <div className="grid max-w-2xl gap-10">
        <dl className="grid grid-cols-1 gap-x-6 sm:grid-cols-[10rem_1fr] gap-y-2.5 text-sm">
          <dt className="label-mono pt-0.5">{t("acc-field-person")}</dt>
          <dd>
            {account.person ? (
              <Link to="/people/$personId" params={{ personId: account.person }} className="hover:text-ember">
                {name(account.person)}
              </Link>
            ) : (
              <span className="text-ink-muted">{t("acc-person-none-lower")}</span>
            )}
          </dd>
          <dt className="label-mono pt-0.5">{t("acc-field-created")}</dt>
          <dd>{moment(account.created_at)}</dd>
        </dl>
        <Section title={t("acc-role")}>
          {editable ? (
            <div className="grid max-w-sm gap-1.5">
              <label htmlFor="account-role" className="sr-only">
                {t("acc-role")}
              </label>
              <Choice
                id="account-role"
                value={account.role}
                options={roleOptions()}
                disabled={lastOwner || account.disabled || change.isPending}
                onChange={(role: Role) => change.mutate({ role })}
              />
              <p className="text-xs text-ink-muted">{lastOwner ? lastOwnerText() : roleHint(account.role)}</p>
            </div>
          ) : (
            <p className="text-sm">{roleLabel(account.role)}</p>
          )}
          <FormError error={change.error} />
        </Section>
        {editable ? (
          <Section title={account.disabled ? t("acc-enable") : t("acc-disable-section")}>
            {account.disabled ? (
              <Button variant="outline" onClick={() => change.mutate({ disabled: false })} disabled={change.isPending}>
                {t("acc-enable")}
              </Button>
            ) : (
              <>
                <p className="mb-4 text-sm text-ink-muted">{lastOwner ? lastOwnerText() : t("acc-disable-hint")}</p>
                <Confirm
                  trigger={
                    <Button variant="destructive" disabled={lastOwner}>
                      {t("acc-disable")}
                    </Button>
                  }
                  title={t("acc-disable-title", { name: account.person_name ?? account.login })}
                  confirm={t("acc-disable-confirm")}
                  onConfirm={() => change.mutateAsync({ disabled: true })}
                >
                  {t("acc-disable-text")}
                </Confirm>
              </>
            )}
          </Section>
        ) : null}
      </div>
    </>
  );
}
