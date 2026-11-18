## Admin accounts, roles and invitations.

acc-title = Accounts
acc-intro = Who can sign in to the admin, and with which role.
acc-invite = Invite…
acc-invite-title = Invite someone
acc-invite-description = You get a link to send them.
acc-invite-sent = { $has_person ->
    [yes] Send this link to <strong>{ $person }</strong>. It works once, for seven days, and will not be shown again.
   *[no] Send this link to the person you invite. It works once, for seven days, and will not be shown again.
}
acc-invite-link = the invitation link
acc-invite-done = Done
acc-role = Role
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
acc-never = never
acc-invitations-empty = No pending invitation.
acc-revoke = Withdraw…
acc-revoke-title = Withdraw this invitation?
acc-revoke-confirm = Withdraw
acc-revoke-text = { $has_person ->
    [yes] The link made for { $person } stops working.
   *[no] Its link stops working.
}
acc-not-found = This account does not exist.
acc-field-person = person
acc-field-created = created
acc-field-seen = last sign-in
acc-enable = Enable again
acc-disable = Disable…
acc-disable-hint = Their journal, connections and memories are kept.
acc-disable-title = Disable { $name }'s account?
acc-disable-confirm = Disable
acc-disable-text = They can no longer sign in. You can enable the account again.
acc-people = Who has access
acc-invitations = Pending invitations
acc-invitations-empty-hint = An invitation is a link that works once, for seven days.
acc-invitation-anyone = Not tied to a household member
acc-invitation-line = { $role } · expires { $expires }
acc-signin = Sign-in
acc-disabled-note = This account can no longer sign in. Its journal, connections and memories are kept.
