# Erreurs de l'API d'administration (`error-<code>`) : montrées telles quelles.

error-unauthenticated = Connectez-vous pour continuer.
error-bad-token = Jeton d'administration absent ou faux.
error-forbidden = Votre compte n'a pas accès à cette fonction.
error-csrf-failed = Requête refusée : rechargez la page et recommencez.
error-unsupported-media-type = Le corps de la requête doit être du JSON.
error-not-found = Ceci n'existe pas ou plus.
error-method-not-allowed = Méthode non permise.
error-http-error = Requête refusée.
error-invalid-request = Requête invalide ({ $fields }).
error-invalid = Action impossible : { $detail }.
error-provider-error = Le service n'a pas pu répondre : { $detail }.
error-invalid-credentials = Identifiant ou mot de passe incorrect.
error-throttled = Trop d'essais. Réessayez dans { $minutes ->
    [one] une minute
   *[other] { $minutes } minutes
}.
error-weak-password = Choisissez un mot de passe d'au moins { $length } caractères.
error-invalid-login = L'identifiant est un e-mail ou un nom d'utilisateur (lettres, chiffres, . _ + @ -).
error-wrong-password = Le mot de passe actuel est incorrect.
error-use-me-password = Pour votre propre mot de passe, passez par votre profil.
error-unknown-locale = Cette langue n'est pas disponible.
error-last-owner = Le foyer doit garder au moins un propriétaire : nommez-en un autre d'abord.
error-conflict = Cet identifiant est déjà pris, ou cette personne a déjà un compte.
error-unknown-person = Choisissez une personne du foyer.
error-person-required = Un compte membre ou invité appartient à une personne du foyer.
error-invitation-unknown = Cette invitation est inconnue.
error-invitation-used = Cette invitation a déjà servi.
error-invitation-expired = Cette invitation a expiré : demandez-en une nouvelle.
error-invitation-revoked = Cette invitation a été retirée.
error-no-connectors = Aucun connecteur n'est installé sur cette instance.
error-connector-unknown = Aucun connecteur « { $kind } » n'est installé.
error-connection-unknown = Cette connexion n'existe pas ou a été supprimée.
error-not-oauth = { $connector } ne se connecte pas par OAuth.
error-oauth = { $connector } se connecte par OAuth.
error-client-incomplete = Indiquez l'identifiant et le secret du client OAuth.
error-client-missing = Enregistrez d'abord le client OAuth de ce service.
error-own-connections-only = Vous ne pouvez connecter un compte que pour vous-même.
error-fields-missing = Champs manquants : { $fields }.
error-provider-refused = Le service a refusé la connexion : { $detail }.
error-unknown-tool = Outils inconnus : { $tools }.
error-invalid-code = Le code est fait de 6 chiffres, lus sur l'appareil.
error-pairing-refused = Aucun appareil n'attend ce code : il est faux ou a expiré.
error-satellite-unknown = Ce satellite n'est pas ou plus appairé.
error-unknown-kind = Catégorie inconnue : { $kind }.
error-task-unknown = Cette tâche n'existe pas ou est déjà terminée.
error-watch-unknown = Cette veille n'existe pas ou est déjà terminée.
error-memory-unknown = Ce souvenir n'existe pas ou plus.
error-memory-shared = Seule l'administration du foyer modifie les souvenirs communs.
error-empty-memory = Pour effacer un souvenir, oubliez-le.
