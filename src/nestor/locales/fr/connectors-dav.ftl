# Le connecteur CalDAV et CardDAV : son nom, sa description, ses champs et le guide affiché avant de le connecter.

connector-dav-title = Agendas et contacts (CalDAV, CardDAV)
connector-dav-description = Les agendas et contacts d'iCloud, Fastmail, Nextcloud ou de tout serveur CalDAV et CardDAV. Des événements peuvent être ajoutés ; les contacts sont en lecture seule.
connector-dav-field-server = Serveur CalDAV (par exemple https://caldav.icloud.com)
connector-dav-field-contacts_server = Serveur CardDAV, s'il est différent
connector-dav-field-username = Identifiant (souvent l'adresse complète)
connector-dav-field-password = Mot de passe d'application
connector-dav-setup =
    Nestor lit vos agendas et vos contacts en CalDAV et CardDAV, et peut ajouter des événements, après
    vous l'avoir demandé. Il ne modifie ni ne supprime jamais un événement ou un contact.

    Utilisez un mot de passe d'application plutôt que votre mot de passe habituel : il ne sert qu'à
    Nestor et se révoque à tout moment.

    - iCloud : https://account.apple.com, « Connexion et sécurité », « Mots de passe pour app ».
      Serveur CalDAV https://caldav.icloud.com, serveur CardDAV https://contacts.icloud.com ;
      l'identifiant est l'adresse de votre compte Apple.
    - Fastmail : « Paramètres », « Confidentialité et sécurité », « Gérer les mots de passe
      d'application », accès « Calendriers (CalDAV) » et « Contacts (CardDAV) ». Serveur CalDAV
      https://caldav.fastmail.com, serveur CardDAV https://carddav.fastmail.com ; l'identifiant est
      votre adresse Fastmail.
    - Nextcloud : « Paramètres personnels », « Sécurité », « Créer un nouveau mot de passe
      d'application ». Serveur https://<votre Nextcloud>/remote.php/dav, pour les deux ; l'identifiant
      est votre nom d'utilisateur Nextcloud.
    - Un autre serveur (Synology, Radicale, Baïkal…) : l'adresse que donne sa documentation pour
      CalDAV, et pour CardDAV si elle diffère.
