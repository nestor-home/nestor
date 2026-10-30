## Admin accounts, roles and invitations.

acc-title = Accounts
acc-intro = Recognising a voice or a face never replaces an account.
acc-tab-accounts = Accounts
acc-tab-invitations = Invitations
acc-invite = Invite…
acc-invite-title = Invite someone
acc-invite-description = They receive a link to choose their password.
acc-invite-sent = { $has_person ->
    [yes] Send this link to <strong>{ $person }</strong>: it works once, for seven days, and will not be shown again.
   *[no] Send this link to the person you invite: it works once, for seven days, and will not be shown again.
}
acc-invite-link = the invitation link
acc-invite-done = Done
acc-email = Email address
acc-email-placeholder = odile@example.com…
acc-role = Role
acc-role-of = Role of { $name }
acc-person = Household member
acc-person-hint = Ties the account to their journal and connections.
acc-person-none = None
acc-person-none-lower = none
acc-inviting = Inviting…
acc-invite-create = Create the invitation
acc-last-owner = Last active owner: the household must keep at least one.
acc-role-changed = { $name } is now { $role }.
acc-disabled-done = { $name }'s account disabled.
acc-enabled-done = { $name }'s account enabled again.
acc-you = you
acc-disabled = disabled
acc-active = active
acc-never-signed-in = never signed in
acc-never = never
acc-invitations-empty = No pending invitation.
acc-invitation-pending = [ pending ] · { $role }{ $has_person ->
    [no] {""}
   *[yes] {" · "}{ $person }
} · expires { $expires }
acc-revoke = Withdraw…
acc-revoke-title = Withdraw this invitation?
acc-revoke-confirm = Withdraw
acc-revoke-text = The link sent to { $email } will stop working.
acc-not-found = This account does not exist.
acc-field-person = person
acc-field-created = created
acc-field-seen = seen
acc-enable = Enable again
acc-disable-section = Disable
acc-disable = Disable…
acc-disable-hint = Their sessions are closed; their journal, connections and memories stay.
acc-disable-title = Disable { $name }'s account?
acc-disable-confirm = Disable
acc-disable-text = Their sessions are closed and they can no longer sign in. You can enable the account again.
