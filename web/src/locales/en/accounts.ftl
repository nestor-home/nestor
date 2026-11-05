## Admin accounts, roles and invitations.

acc-title = Accounts
acc-intro = Who can sign in to the admin, and with which role.
acc-tab-accounts = Accounts
acc-tab-invitations = Invitations
acc-invite = Invite…
acc-invite-title = Invite someone
acc-invite-description = You get a link to send them.
acc-invite-sent = { $has_person ->
    [yes] Send this link to <strong>{ $person }</strong>. It works once, for seven days, and will not be shown again.
   *[no] Send this link to the person you invite. It works once, for seven days, and will not be shown again.
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
acc-last-owner = At least one active owner is required.
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
acc-field-seen = last sign-in
acc-enable = Enable again
acc-disable-section = Disable
acc-disable = Disable…
acc-disable-hint = Their journal, connections and memories are kept.
acc-disable-title = Disable { $name }'s account?
acc-disable-confirm = Disable
acc-disable-text = They can no longer sign in. You can enable the account again.
