# The CalDAV and CardDAV connector: its name, description, fields and the guide shown before connecting it.

connector-dav-title = Calendars and contacts (CalDAV, CardDAV)
connector-dav-description = The calendars and contacts of iCloud, Fastmail, Nextcloud or any CalDAV and CardDAV server. Events can be added; contacts are read only.
connector-dav-field-server = CalDAV server (e.g. https://caldav.icloud.com)
connector-dav-field-contacts_server = CardDAV server, when it is another one
connector-dav-field-username = Login (often the full address)
connector-dav-field-password = App password
connector-dav-setup =
    Nestor reads your calendars and contacts over CalDAV and CardDAV, and can add events, after asking
    you. It never changes nor deletes an event or a contact.

    Use an app password rather than your usual password: it only serves Nestor and can be revoked at
    any time.

    - iCloud: https://account.apple.com, “Sign-In and Security”, “App-Specific Passwords”. CalDAV
      server https://caldav.icloud.com, CardDAV server https://contacts.icloud.com; the login is your
      Apple Account address.
    - Fastmail: “Settings”, “Privacy & Security”, “Manage app passwords”, access “Calendars (CalDAV)”
      and “Contacts (CardDAV)”. CalDAV server https://caldav.fastmail.com, CardDAV server
      https://carddav.fastmail.com; the login is your Fastmail address.
    - Nextcloud: “Personal settings”, “Security”, “Create new app password”. Server
      https://<your Nextcloud>/remote.php/dav, for both; the login is your Nextcloud user name.
    - Another server (Synology, Radicale, Baïkal…): the address its documentation gives for CalDAV,
      and for CardDAV when it differs.
