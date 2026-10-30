# The IMAP connector: its name, description, fields and the guide shown before connecting it.

connector-imap-title = Mailbox (IMAP)
connector-imap-description = Search and read a mailbox over IMAP; new mail can feed watches. Read only.
connector-imap-field-host = IMAP server (e.g. imap.free.fr)
connector-imap-field-port = Port
connector-imap-field-username = Login (often the full address)
connector-imap-field-password = App password
connector-imap-field-folder = Watched folder
connector-imap-setup =
    Nestor reads your mailbox over IMAP, read only: it never moves, deletes nor flags a message.

    Use an app password rather than your usual password: it only serves Nestor and can be revoked at
    any time without touching anything else. Most providers require one as soon as two-step
    verification is on.

    - Gmail: turn on two-step verification, then create an app password at
      https://myaccount.google.com/apppasswords. Server imap.gmail.com, port 993. (The “Google”
      connector is simpler and safer for Gmail.)
    - iCloud: https://account.apple.com, “Sign-In and Security”, “App-Specific Passwords”. Server
      imap.mail.me.com, port 993; the login is your iCloud address.
    - Outlook / Hotmail: since September 2024, Microsoft no longer accepts passwords over IMAP for
      personal accounts (OAuth sign-in required): this connector cannot connect to them.
    - Free: server imap.free.fr, port 993, your address and your Free mailbox password.
    - Orange: server imap.orange.fr, port 993, your address and your mail password.

    Then fill in the server, the port (993: encrypted connection), the login (often your full
    address), the password and the folder to watch (INBOX for the inbox). Port 143 without encryption
    is not accepted, except for a local server (a bridge such as Proton Bridge).
