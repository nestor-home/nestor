# Le connecteur Microsoft 365 : son nom, sa description et le guide affiché avant de le connecter.

connector-microsoft-title = Microsoft 365
connector-microsoft-description = Mails Outlook (lecture seule, les nouveaux mails alimentent les veilles) et agenda, OneDrive (lecture seule) et To Do, pour un compte professionnel ou personnel.
connector-microsoft-setup =
    Nestor se connecte à Microsoft avec votre propre inscription d'application. Comptez une dizaine
    de minutes, une seule fois par foyer.

    1. Ouvrez les inscriptions d'applications du portail Azure
       (https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade), connectez-
       vous avec n'importe quel compte Microsoft, puis « Nouvelle inscription ».
    2. Donnez-lui un nom (par exemple « Nestor »). Sous « Types de comptes pris en charge », choisissez
       « Comptes dans un annuaire d'organisation et comptes Microsoft personnels ». Sous « URI de
       redirection », choisissez « Web » et collez exactement l'adresse de retour affichée par Nestor
       ci-dessous. Inscrivez.
    3. Dans « API autorisées », « Ajouter une autorisation », « Microsoft Graph », « Autorisations
       déléguées », ajoutez : offline_access, openid, email, User.Read, Mail.Read,
       MailboxSettings.Read, Calendars.ReadWrite, Files.Read et Tasks.ReadWrite. Nestor ne peut ni
       envoyer, ni supprimer, ni modifier vos mails, ni modifier vos fichiers ; il peut ajouter des
       événements et des tâches, après vous l'avoir demandé. Pour un compte professionnel, votre
       administrateur devra peut-être accorder ces autorisations.
    4. Dans « Certificats et secrets », « Nouveau secret client » : copiez sa Valeur (pas son ID), qui
       n'est plus affichée ensuite. Un secret expire (24 mois au plus) : créez-en un nouveau avant.
    5. Dans « Vue d'ensemble », copiez l'« ID d'application (client) ».
    6. Collez l'ID client et le secret dans Nestor, puis cliquez sur « Connecter », et autorisez
       l'accès.

    Pour couper l'accès : déconnectez le compte dans Nestor, ou retirez Nestor sur
    https://account.live.com/consent/Manage (compte personnel) ou https://myapps.microsoft.com
    (compte professionnel).
