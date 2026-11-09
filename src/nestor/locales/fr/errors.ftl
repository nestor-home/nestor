# Erreurs de l'API d'administration (`error-<code>`) : montrées telles quelles.

error-unauthenticated = Connectez-vous pour continuer.
error-bad-token = Token d'admin manquant ou invalide.
error-forbidden = Votre compte n'a pas accès à cette fonction.
error-csrf-failed = Requête refusée : rechargez la page et recommencez.
error-unsupported-media-type = Le corps de la requête doit être du JSON.
error-not-found = Introuvable.
error-method-not-allowed = Méthode non permise.
error-http-error = Requête refusée.
error-invalid-request = Requête invalide ({ $fields }).
error-invalid = Action impossible : { $detail }.
error-provider-error = Le service ne répond pas : { $detail }.
error-invalid-credentials = Identifiant ou mot de passe incorrect.
error-throttled = Trop d'essais. Réessayez dans { $minutes ->
    [one] une minute
   *[other] { $minutes } minutes
}.
error-weak-password = Choisissez un mot de passe d'au moins { $length } caractères.
error-invalid-login = L'identifiant est un e-mail ou un nom d'utilisateur (lettres, chiffres, . _ + @ -).
error-wrong-password = Le mot de passe actuel est incorrect.
error-use-me-password = Changez votre mot de passe depuis votre profil.
error-unknown-locale = Cette langue n'est pas disponible.
error-last-owner = Le foyer doit garder au moins un propriétaire : nommez-en un autre d'abord.
error-conflict = Cet identifiant est déjà pris, ou cette personne a déjà un compte.
error-unknown-person = Choisissez une personne du foyer.
error-person-required = Un compte membre ou invité doit être lié à une personne du foyer.
error-invitation-unknown = Invitation introuvable.
error-invitation-used = Cette invitation a déjà servi.
error-invitation-expired = Cette invitation a expiré : demandez-en une nouvelle.
error-invitation-revoked = Cette invitation a été retirée.
error-no-connectors = Aucun connecteur n'est installé sur cette instance.
error-connector-unknown = Aucun connecteur « { $kind } » n'est installé.
error-connection-unknown = Cette connexion n'existe pas ou a été supprimée.
error-not-oauth = { $connector } ne se connecte pas par OAuth.
error-oauth = { $connector } se connecte par OAuth.
error-client-incomplete = Renseignez l'ID client et le secret OAuth.
error-client-missing = Enregistrez d'abord le client OAuth de ce service.
error-own-connections-only = Vous ne pouvez connecter un compte que pour vous-même.
error-fields-missing = Champs manquants : { $fields }.
error-provider-refused = Le service a refusé la connexion : { $detail }.
error-unknown-tool = Outils inconnus : { $tools }.
error-invalid-code = Le code fait 6 chiffres, affichés ou dits par l'appareil.
error-pairing-refused = Aucun appareil n'attend ce code : il est faux, a expiré, ou l'appareil est déjà appairé.
error-not-a-device-code-method = Cette méthode ne passe pas par un code saisi ici.
error-addition-unknown = Ajout introuvable.
error-addition-over = Cet ajout est terminé : appareil appairé, ajout annulé ou expiré.
error-too-many-additions = Trop d'ajouts sont en cours. Annulez-en un d'abord.
error-pending-unknown = Cet appareil n'attend plus d'appairage.
error-identify-unsupported = Cet appareil ne prend pas en charge l'identification.
error-satellite-offline = Ce satellite n'est pas connecté en ce moment.
error-update-unsupported = Cet appareil ne prend pas en charge les mises à jour.
error-update-unavailable = Ce satellite n'a trouvé aucune nouvelle version.
error-satellite-unknown = Ce satellite n'est pas appairé.
error-task-unknown = Cette tâche n'existe pas ou est déjà terminée.
error-watch-unknown = Cette veille n'existe pas ou est déjà terminée.
error-schedule-unknown = Ce rappel n'existe pas ou est déjà passé.
error-confirmation-unknown = Cette demande n'attend plus votre accord : déjà répondue, ou expirée.
error-memory-unknown = Souvenir introuvable.
error-memory-shared = Seuls les administrateurs modifient les souvenirs communs.
error-empty-memory = Un souvenir ne peut pas être vide. Pour l'effacer, oubliez-le.
error-journal-entry-unknown = Entrée du journal introuvable.
error-cross-origin = Requête refusée : elle ne vient pas de cette admin.
error-person-unknown = Cette personne ne fait pas partie du foyer.
error-config-unavailable = Nestor n'a pas été lancé avec un fichier de configuration : rien à modifier.
error-no-secret-key = NESTOR_SECRET_KEY n'est pas définie : impossible de stocker des secrets.
error-config-invalid = La configuration est inutilisable ({ $count ->
    [one] un problème
   *[other] { $count } problèmes
}) : rien n'a été écrit.
error-config-history-unknown = Version de configuration introuvable.
error-secret-in-use = Ce secret sert encore à { $paths } : retirez d'abord ces références.
error-secret-unknown = Ce secret n'est pas défini.
error-restart-unconfirmed = Confirmez le redémarrage : les conversations en cours seront coupées un instant.
error-update-unconfirmed = Confirmez la mise à jour : Nestor redémarre une fois installée.
error-update-not-installable = Cette version ne peut pas être installée d'ici.

error-voices-off = La reconnaissance des voix est désactivée : choisissez un modèle sous voices dans la configuration.
error-voice-not-yours = Chacun enregistre sa propre voix. Un propriétaire peut le faire pour quelqu'un sans compte.
error-audio-format = L'enregistrement doit être un WAV mono 16 bits à 16 kHz.
