## Connexions : comptes connectés, catalogue, connecter un service, les pages d'une connexion.

conn-title = Connexions
conn-intro = Les jetons sont chiffrés et jamais montrés au modèle ; { $assistant } n'utilise que les outils que vous activez.
conn-connect-service = Connecter un service
conn-tab-accounts = Comptes connectés
conn-tab-catalogue = Catalogue

conn-empty = Aucun compte connecté pour l'instant.
conn-empty-hint = Une boîte mail lui permet de surveiller ce qui arrive ; un serveur MCP lui donne des outils.
conn-open-catalogue = Ouvrir le catalogue
conn-calls-today = { $count ->
    [0] aucun appel aujourd'hui
    [one] 1 appel aujourd'hui
   *[other] { $count } appels aujourd'hui
}
conn-no-connector = Aucun connecteur n'est installé sur cette instance.
conn-feeds-watches = alimente les veilles
conn-accounts-count = { $count ->
    [one] 1 compte
   *[other] { $count } comptes
}
conn-client-to-create = client à créer
conn-connect-ellipsis = Connecter…

conn-connect = Connecter
conn-connecting = Connexion…
conn-redirecting = Redirection vers le service…
conn-connected = Connecté
conn-connect-account = Connecter un compte
conn-oauth-consent = Vous donnerez votre accord sur la page du service, puis reviendrez ici.
conn-account-of = Compte de
conn-account-of-hint = Ses outils serviront pour cette personne, ou pour tout le foyer.
conn-field-optional = { $label } (facultatif)
conn-client-first = Enregistrez d'abord le client OAuth du foyer.
conn-status-redirecting = [ en route vers le fournisseur ]
conn-status-pending = [ en cours ]
conn-reconnect-note = Reconnexion : l'ancien accès reste actif jusqu'à ce que le nouveau fonctionne, et ses réglages sont repris.

conn-client-title = Client OAuth du foyer
conn-client-registered = enregistré
conn-client-missing = à créer
conn-client-id = Identifiant
conn-client-why = Chaque foyer déclare sa propre application chez le fournisseur : aucun secret n'est partagé entre instances.
conn-redirect-uri = URI de redirection à déclarer chez le fournisseur
conn-redirect-uri-label = l'URI de redirection
conn-relayed = Sans HTTPS, le fournisseur renvoie votre navigateur vers cette page relais publique, qui le redirige aussitôt ici. Le code d'autorisation y passe sans jamais être utilisable sans la clé gardée par cette instance.
conn-client-replace-ellipsis = Remplacer le client…
conn-client-register-ellipsis = Enregistrer le client…
conn-client-replace-title = Remplacer le client OAuth
conn-client-register-title = Enregistrer le client OAuth
conn-client-replace-note = Seulement s'il a changé chez le fournisseur : les comptes connectés le gardent.
conn-client-saved = Client OAuth enregistré : vous pouvez connecter un compte.
conn-client-id-field = Identifiant du client (client ID)
conn-client-secret-field = Secret du client (client secret)
conn-client-register = Enregistrer le client

conn-tools = Outils
conn-tools-saved = Réglages des outils enregistrés.
conn-no-tools = Ce service n'apporte pas d'outil.
conn-confirm-writes = Demander confirmation avant d'écrire
conn-confirm-writes-hint = Les actions sensibles, comme envoyer, la demandent toujours.
conn-unsaved = ● modifications non enregistrées

conn-sections = Sections de la connexion
conn-tab-overview = Aperçu
conn-tab-activity = Activité
conn-tab-settings = Réglages
conn-owner = compte de { $name }
conn-connected-at = connecté { $when }
conn-broken = { $assistant } ne peut plus utiliser ce compte : ses outils sont masqués et ses veilles attendent.
conn-reconnect = Reconnecter
conn-reconnect-ellipsis = Reconnecter…
conn-reconnect-hint = Pour changer de compte ou de mot de passe : le nouvel accès remplace l'ancien et garde ses réglages d'outils.
conn-summary-owned = Le compte { $service } de { $name }.
conn-summary-household = Un service { $service } pour tout le foyer.
conn-summary-usage = { $count ->
    [0] { $assistant } ne l'a pas utilisé aujourd'hui.
    [one] { $assistant } l'a utilisé une fois aujourd'hui.
   *[other] { $assistant } l'a utilisé { $count } fois aujourd'hui.
}
conn-summary-usage-last = { $count ->
    [0] { $assistant } ne l'a pas utilisé aujourd'hui ; la dernière fois { $ago }.
    [one] { $assistant } l'a utilisé une fois aujourd'hui, la dernière { $ago }.
   *[other] { $assistant } l'a utilisé { $count } fois aujourd'hui, la dernière { $ago }.
}
conn-summary-watches = { $count ->
    [one] Il alimente 1 veille.
   *[other] Il alimente { $count } veilles.
}
conn-summary-tools = { $enabled } outils actifs sur { $total }{ $writes ->
    [0] .
    [one] , dont 1 qui écrit{ $confirm ->
        [yes] , toujours après confirmation.
       *[no] {" "}sans confirmation.
    }
   *[other] , dont { $writes } qui écrivent{ $confirm ->
        [yes] , toujours après confirmation.
       *[no] {" "}sans confirmation.
    }
}
conn-latest-uses = Dernières utilisations
conn-never-used = { $assistant } ne s'en est pas encore servi.
conn-no-activity = Aucun événement n'implique encore cette connexion.
conn-disconnected = Compte { $account } déconnecté : ses accès ont été révoqués et oubliés.
conn-read-only = Votre rôle ne permet pas de modifier cette connexion.
conn-disconnect = Déconnecter
conn-disconnect-ellipsis = Déconnecter…
conn-disconnect-hint = L'accès est révoqué chez le fournisseur quand c'est possible, puis tous les secrets de ce compte sont oubliés.
conn-disconnect-title = Déconnecter { $account } ?
conn-disconnect-consequence = Ses outils disparaissent aussitôt et les veilles qui en dépendent s'arrêtent. Pour le retrouver, il faudra le connecter à nouveau.
conn-account-connected = Compte { $account } connecté.

conn-failed-crumb = Échec
conn-failed-denied = Autorisation refusée
conn-failed-denied-text = L'accès a été refusé sur la page du service : rien n'a été connecté.
conn-failed-expired = Demande d'autorisation expirée
conn-failed-expired-text = Plus de dix minutes se sont écoulées entre le départ et le retour : recommencez.
conn-failed-unknown = Demande d'autorisation inconnue
conn-failed-unknown-text = Ce retour ne correspond à aucune connexion lancée depuis cette session. Recommencez depuis le catalogue.
conn-failed-exchange = Échange refusé par le service
conn-failed-exchange-text = Le service n'a pas accepté le code d'autorisation. Vérifiez le client OAuth puis recommencez.
conn-failed-other = Le service a renvoyé une erreur
conn-failed-other-text = Erreur indiquée par le service : « { $error } ».
conn-failed-no-code = aucun code
conn-failed-retry = Recommencer
conn-failed-back = Revenir aux connexions
