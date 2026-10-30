# The Google (Gmail) connector: its name, description and the guide shown before connecting it.

connector-google-title = Google (Gmail)
connector-google-description = Search and read Gmail; new inbox mail can feed watches. Read only.
connector-google-setup =
    Nestor connects to Google with your own OAuth client: no shared secret ships with Nestor. Allow
    about ten minutes, once per household.

    1. Open the Google Cloud console (https://console.cloud.google.com/), choose “Select a project”,
       then “New project”, give it a name (for instance “Nestor”) and create it. Check that it is
       selected at the top of the page.
    2. Enable the Gmail API: https://console.cloud.google.com/apis/library/gmail.googleapis.com, then
       “Enable”.
    3. Configure the consent screen in Google Auth Platform
       (https://console.cloud.google.com/auth/branding, “Get started” if it does not exist yet):
       - App information: a name (“Nestor”) and your address as the support email;
       - Audience: “External”;
       - Contact information: your address; accept the user data policy, then “Create”.
    4. In “Data access”, add the scopes openid, email and
       https://www.googleapis.com/auth/gmail.readonly (read only: Nestor can neither send, delete nor
       change your mail).
    5. In “Audience”, click “Publish app” to move it “In production”. This matters: while the app stays
       “Testing”, Google expires the authorisation after 7 days and the account would have to be
       reconnected every week. No need to ask Google for verification: the app only serves you.
    6. In “Clients”, choose “Create client”, type “Web application”. Under “Authorised redirect URIs”,
       paste exactly the return address Nestor shows below. Create, then copy the client ID and the
       client secret (the secret is not shown again).
    7. Paste the client ID and secret into Nestor, then click “Connect”. Google shows “Google hasn't
       verified this app”: it is your own app, choose “Advanced”, then “Go to Nestor (unsafe)”, and
       allow access.

    A new client can take a few minutes (rarely a few hours) to work. To cut access: disconnect the
    account in Nestor, or remove it at https://myaccount.google.com/permissions.
