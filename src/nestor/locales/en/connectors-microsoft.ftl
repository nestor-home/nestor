# The Microsoft 365 connector: its name, description and the guide shown before connecting it.

connector-microsoft-title = Microsoft 365
connector-microsoft-description = Outlook mail (read only, new mail feeds watches) and calendar, OneDrive (read only) and To Do, for a work or personal account.
connector-microsoft-setup =
    Nestor connects to Microsoft with your own app registration. Allow about ten minutes, once per
    household.

    1. Open App registrations in the Azure portal
       (https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade), sign in
       with any Microsoft account, then “New registration”.
    2. Name it (for instance “Nestor”). Under “Supported account types”, choose “Accounts in any
       organizational directory and personal Microsoft accounts”. Under “Redirect URI”, choose “Web”
       and paste exactly the return address Nestor shows below. Register.
    3. In “API permissions”, “Add a permission”, “Microsoft Graph”, “Delegated permissions”, add:
       offline_access, openid, email, User.Read, Mail.Read, MailboxSettings.Read,
       Calendars.ReadWrite, Files.Read and Tasks.ReadWrite. Nestor can neither send, delete nor change
       your mail, nor change your files; it can add events and tasks, after asking you. For a work
       account, your administrator may have to grant these permissions.
    4. In “Certificates & secrets”, “New client secret”: copy its Value (not its ID), which is not
       shown again. A secret expires (24 months at most): create a new one before then.
    5. In “Overview”, copy the “Application (client) ID”.
    6. Paste the client ID and the secret into Nestor, then click “Connect”, and allow access.

    To cut access: disconnect the account in Nestor, or remove Nestor at
    https://account.live.com/consent/Manage (personal account) or https://myapps.microsoft.com (work
    account).
