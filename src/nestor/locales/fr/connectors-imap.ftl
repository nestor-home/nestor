# Le connecteur IMAP : son nom, sa description, ses champs et le guide affiché avant de le connecter.

connector-imap-title = Boîte mail (IMAP)
connector-imap-description = Recherche et lecture d'une boîte mail en IMAP, en lecture seule. Les nouveaux mails alimentent les veilles.
connector-imap-field-host = Serveur IMAP (ex. imap.free.fr)
connector-imap-field-port = Port
connector-imap-field-username = Identifiant (souvent l'adresse complète)
connector-imap-field-password = Mot de passe d'application
connector-imap-field-folder = Dossier surveillé
connector-imap-setup =
    Nestor lit votre boîte en IMAP, en lecture seule : il ne déplace, ne supprime ni ne marque aucun mail.

    Utilisez un mot de passe d'application plutôt que votre mot de passe habituel : il ne sert qu'à Nestor
    et se révoque à tout moment. La plupart des fournisseurs l'exigent avec la validation en deux étapes.

    - Gmail : activez la validation en deux étapes, puis créez un mot de passe d'application sur
      https://myaccount.google.com/apppasswords. Serveur imap.gmail.com, port 993. (Le connecteur
      « Google » est plus simple et plus sûr pour Gmail.)
    - iCloud : https://account.apple.com, « Connexion et sécurité », « Mots de passe pour app ».
      Serveur imap.mail.me.com, port 993 ; l'identifiant est votre adresse iCloud.
    - Outlook / Hotmail : depuis septembre 2024, Microsoft n'accepte plus de mot de passe en IMAP pour
      les comptes personnels (connexion OAuth obligatoire) : ce connecteur ne peut pas s'y connecter.
    - Free : serveur imap.free.fr, port 993, votre adresse et le mot de passe de votre boîte Free.
    - Orange : serveur imap.orange.fr, port 993, votre adresse et votre mot de passe de messagerie.

    Le dossier de la boîte de réception est INBOX. Le port 143 sans chiffrement n'est accepté que pour un
    serveur local (un pont comme Proton Bridge).
