## Connexions : comptes connectés, catalogue, connecter un service, les pages d'une connexion.

conn-title = Connexions
conn-intro = Jetons chiffrés, jamais montrés au modèle. Seuls les outils activés sont utilisés.
conn-connect-service = Connecter un service
conn-tab-accounts = Comptes connectés
conn-tab-catalogue = Catalogue

conn-empty = Aucun compte connecté pour l'instant.
conn-empty-hint = Une boîte mail pour les veilles, un serveur MCP pour des outils.
conn-open-catalogue = Ouvrir le catalogue
conn-calls-today = { $count ->
    [0] aucun appel aujourd'hui
    [one] 1 appel aujourd'hui
   *[other] { $count } appels aujourd'hui
}
conn-no-connector = Aucun connecteur installé.
conn-feeds-watches = alimente les veilles
conn-accounts-count = { $count ->
    [one] 1 compte
   *[other] { $count } comptes
}
conn-client-to-create = client OAuth manquant
conn-connect-ellipsis = Connecter…

conn-connect = Connecter
conn-connecting = Connexion…
conn-redirecting = Redirection vers le service…
conn-connected = Connecté
conn-connect-account = Connecter un compte
conn-oauth-consent = Vous autoriserez l'accès sur la page du service.
conn-account-of = Compte de
conn-account-of-hint = Une personne, ou tout le foyer.
conn-field-optional = { $label } (facultatif)
conn-client-first = Enregistrez d'abord le client OAuth.
conn-status-redirecting = [ redirection… ]
conn-status-pending = [ en cours ]
conn-reconnect-note = L'ancien accès reste actif jusqu'à ce que le nouveau fonctionne. Les réglages sont conservés.
conn-presets = Serveurs connus
conn-credentials = Jeton ou client OAuth
conn-redirect-uri-service = Adresse de redirection à déclarer sur le service
conn-field-kept = Laissé vide : repris du compte reconnecté.

conn-client-title = Client OAuth
conn-client-registered = enregistré
conn-client-missing = manquant
conn-client-id = Client ID
conn-client-why = Chaque foyer crée sa propre app OAuth chez le fournisseur : aucun secret n'est partagé.
conn-redirect-uri = URI de redirection à déclarer chez le fournisseur
conn-redirect-uri-label = l'URI de redirection
conn-relayed = Sans HTTPS, le fournisseur passe par cette page relais publique, qui vous renvoie aussitôt ici. Le code d'autorisation y transite, inutilisable sans la clé de cette instance.
conn-client-replace-ellipsis = Remplacer le client…
conn-client-register-ellipsis = Enregistrer le client…
conn-client-replace-title = Remplacer le client OAuth
conn-client-register-title = Enregistrer le client OAuth
conn-client-replace-note = Seulement s'il a changé chez le fournisseur. Les comptes connectés continuent de fonctionner.
conn-client-saved = Client OAuth enregistré : vous pouvez connecter un compte.
conn-client-id-field = Client ID
conn-client-secret-field = Client secret
conn-client-register = Enregistrer le client

conn-tools = Outils
conn-tools-saved = Réglages des outils enregistrés.
conn-no-tools = Aucun outil.
conn-confirm-writes = Demander confirmation avant d'écrire
conn-confirm-writes-hint = Les actions sensibles, comme un envoi, la demandent toujours.
conn-unsaved = ● modifications non enregistrées

conn-sections = Sections de la connexion
conn-tab-overview = Aperçu
conn-tab-activity = Activité
conn-tab-settings = Réglages
conn-owner = compte de { $name }
conn-connected-at = connecté { $when }
conn-broken = { $assistant } ne peut plus utiliser ce compte : ses outils et ses veilles sont suspendus.
conn-reconnect = Reconnecter
conn-reconnect-ellipsis = Reconnecter…
conn-reconnect-hint = Pour changer de compte ou de mot de passe. Les réglages des outils sont conservés.
conn-summary-owned = Le compte { $service } de { $name }.
conn-summary-household = { $service } pour tout le foyer.
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
    [one] , dont 1 en écriture{ $confirm ->
        [yes] , avec confirmation.
       *[no] , sans confirmation.
    }
   *[other] , dont { $writes } en écriture{ $confirm ->
        [yes] , avec confirmation.
       *[no] , sans confirmation.
    }
}
conn-latest-uses = Dernières utilisations
conn-never-used = { $assistant } ne s'en est pas encore servi.
conn-no-activity = Aucune activité pour l'instant.
conn-disconnected = Compte { $account } déconnecté.
conn-read-only = Votre rôle ne permet pas de modifier cette connexion.
conn-disconnect = Déconnecter
conn-disconnect-ellipsis = Déconnecter…
conn-disconnect-hint = Révoque l'accès chez le fournisseur si possible, puis supprime les secrets du compte.
conn-disconnect-title = Déconnecter { $account } ?
conn-disconnect-consequence = Ses outils disparaissent et les veilles qui en dépendent s'arrêtent.
conn-account-connected = Compte { $account } connecté.

conn-failed-crumb = Échec
conn-failed-denied = Autorisation refusée
conn-failed-denied-text = Rien n'a été connecté.
conn-failed-expired = Demande d'autorisation expirée
conn-failed-expired-text = Plus de dix minutes se sont écoulées. Recommencez.
conn-failed-unknown = Demande d'autorisation inconnue
conn-failed-unknown-text = Elle n'a pas été lancée depuis cette session. Recommencez depuis le catalogue.
conn-failed-exchange = Code refusé par le service
conn-failed-exchange-text = Vérifiez le client OAuth, puis recommencez.
conn-failed-other = Le service a renvoyé une erreur
conn-failed-other-text = Erreur : « { $error } ».
conn-failed-no-code = aucun code
conn-failed-retry = Recommencer
conn-failed-back = Revenir aux connexions
