## Signing in and accepting an invitation.

auth-footer = nestor · an open runtime for home agents
auth-login-title = Sign in
auth-password = Password
auth-sign-in = Sign in
auth-signing-in = Signing in…
auth-invitation-title = Invitation
auth-invitation-invalid = This link was already used or has expired. Ask whoever invited you for a new one.
auth-go-to-login = Go to sign-in
auth-welcome = Welcome
auth-invitation-intro = You are invited as <strong>{ $role }</strong>{ $has_person ->
    [no] {""}
   *[yes] , for { $person }
}. Choose a login and a password.
auth-password-hint = At least { $min } characters. A sentence works very well.
auth-password-repeat = Confirm the password
auth-password-too-short = At least { $min } characters. Add a few words.
auth-password-mismatch = The passwords do not match. Type the same one in both fields.
auth-accept = Accept the invitation
auth-accepting = Creating the account…
auth-login = Login
auth-login-hint = Letters and digits.
auth-login-taken = This login is taken. Choose another one.
auth-login-help = The login is the one chosen with the invitation, not your name. An owner can set a new password from Accounts.
auth-scene = The home at this hour
auth-line-login = { $part ->
    [night] Still up?
    [evening] Good evening.
   *[day] Hello.
} Sign in and I'll tell you how the house is doing.
auth-line-invitation = { $part ->
    [night] Welcome, even this late.
    [evening] Good evening, and welcome.
   *[day] Welcome.
} Choose how you sign in: I'll know you from then on.
auth-line-checking = One moment, I'm looking for your invitation.
auth-line-invalid = I can't find this invitation.
