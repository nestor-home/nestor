## Connexions : comptes connectés, catalogue, connecter un service, les pages d'une connexion.

conn-title = Connexions
conn-intro = Jetons chiffrés, jamais montrés au modèle. Seuls les outils activés sont utilisés.
conn-connect-service = Connecter un service

conn-empty = Aucun compte connecté pour l'instant.
conn-empty-hint = Une boîte mail pour les veilles, un serveur MCP pour des outils.
conn-open-catalogue = Ouvrir le catalogue
conn-no-connector = Aucun connecteur installé.
conn-feeds-watches = alimente les veilles
conn-accounts-count = { $count ->
    [one] 1 compte
   *[other] { $count } comptes
}
conn-client-to-create = client OAuth manquant

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
conn-unsaved = Modifications non enregistrées.

conn-sections = Sections de la connexion
conn-tab-overview = Aperçu
conn-tab-activity = Activité
conn-tab-settings = Réglages
conn-connected-at = connecté { $when }
conn-broken = { $assistant } ne peut plus utiliser ce compte : ses outils et ses veilles sont suspendus.
conn-reconnect = Reconnecter
conn-reconnect-ellipsis = Reconnecter…
conn-reconnect-hint = Pour changer de compte ou de mot de passe. Les réglages des outils sont conservés.
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

conn-services = Dans un message
conn-services-hint = Écrivez l'identifiant dans une discussion pour diriger { $assistant } vers ce compte.
conn-service-unnamed = une fois reconnecté
conn-failed-crumb = Échec
conn-failed-denied = Autorisation refusée
conn-failed-denied-text = Rien n'a été connecté.
conn-failed-expired = Demande d'autorisation expirée
conn-failed-expired-text = Plus de dix minutes se sont écoulées.
conn-failed-unknown = Demande d'autorisation inconnue
conn-failed-unknown-text = Elle n'a pas été lancée depuis cette session.
conn-failed-exchange = Code refusé par le service
conn-failed-exchange-text = Le service n'a pas accepté le code avec le client OAuth enregistré ici.
conn-failed-forbidden = Connexion plus autorisée
conn-failed-forbidden-text = Le compte qui l'a lancée ne peut plus connecter ce service.
conn-failed-provider = Le service n'a pas donné son accord
conn-failed-other = Le service a renvoyé une erreur
conn-failed-other-text = Erreur : « { $error } ».
conn-failed-no-code = aucun code
conn-failed-retry = Recommencer
conn-failed-back = Revenir aux connexions

conn-lanes = Comptes affichés
conn-lane-all = Tous
conn-lane-attention = À reconnecter
conn-attention-title = À reconnecter
conn-attention-empty = Je peux utiliser tous les comptes.
conn-working-title = Connectés
conn-fix-reauth = Le service n'accepte plus l'accès qu'il avait donné. Reconnectez le compte : ses réglages sont conservés.
conn-fix-error = Le service n'a pas répondu comme attendu. Vérifiez la raison donnée, puis reconnectez le compte si cela dure.
conn-last-used = utilisé
conn-never-used-short = jamais utilisé

conn-catalogue = Catalogue
conn-catalogue-lede = Un compte appartient à une personne ou à tout le foyer : vous le choisissez en le connectant.
conn-catalogue-read-only = Votre rôle ne permet pas de connecter un service.
conn-group-accounts = Mail, agendas et fichiers
conn-group-tools = Serveurs d'outils
conn-other-server = Un autre serveur

conn-glance = En bref
conn-figure-calls = Appels aujourd'hui
conn-figure-tools = Outils activés
conn-figure-writes = { $count ->
    [0] aucun ne peut écrire
    [one] 1 peut écrire
   *[other] { $count } peuvent écrire
}
conn-figure-confirm = Demande avant d'écrire
conn-yes = Oui
conn-no = Non
conn-figure-watches = Veilles alimentées
conn-figure-watches-note = { $count ->
    [0] aucune ne dépend de ce compte
   *[other] elles s'arrêtent si vous déconnectez
}
conn-who = Qui peut s'en servir
conn-who-owner = { $assistant } ne s'en sert que pour { $name }.
conn-who-household = { $assistant } s'en sert pour tout le foyer.

conn-failed-next = Étape suivante
conn-failed-denied-next = Recommencez et acceptez l'accès sur la page du service.
conn-failed-expired-next = Recommencez et terminez sur la page du service sans attendre.
conn-failed-unknown-next = Recommencez depuis le catalogue.
conn-failed-exchange-next = Vérifiez le client OAuth, puis recommencez.
conn-failed-forbidden-next = Connectez-vous avec un compte qui le peut, puis recommencez.
conn-failed-provider-next = Recommencez. Si cela se reproduit, vérifiez le client OAuth dans la console du service.
conn-failed-other-next = Recommencez. Si cela se reproduit, cherchez cette erreur dans la documentation du service.
