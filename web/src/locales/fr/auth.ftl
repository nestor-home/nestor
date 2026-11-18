## Connexion et acceptation d'une invitation.

auth-footer = nestor · un runtime ouvert pour les agents de la maison
auth-login-title = Connexion
auth-password = Mot de passe
auth-sign-in = Se connecter
auth-signing-in = Connexion…
auth-invitation-title = Invitation
auth-invitation-invalid = Ce lien a déjà servi ou a expiré. Demandez-en un nouveau à la personne qui vous a invité·e.
auth-go-to-login = Aller à la connexion
auth-welcome = Bienvenue
auth-invitation-intro = Vous êtes invité·e comme <strong>{ $role }</strong>{ $has_person ->
    [no] {""}
   *[yes] , pour { $person }
}. Choisissez un identifiant et un mot de passe.
auth-password-hint = Au moins { $min } caractères. Une phrase marche très bien.
auth-password-repeat = Confirmez le mot de passe
auth-password-too-short = Au moins { $min } caractères. Ajoutez quelques mots.
auth-password-mismatch = Les mots de passe ne correspondent pas. Tapez le même dans les deux champs.
auth-accept = Accepter l'invitation
auth-accepting = Création du compte…
auth-login = Identifiant
auth-login-hint = Lettres et chiffres.
auth-login-taken = Cet identifiant est pris. Choisissez-en un autre.
auth-login-help = L'identifiant est celui choisi avec l'invitation, pas votre nom. Un propriétaire peut définir un nouveau mot de passe depuis Comptes.
auth-scene = La maison à cette heure
auth-line-login = { $part ->
    [night] Encore debout ?
    [evening] Bonsoir.
   *[day] Bonjour.
} Connectez-vous et je vous dis comment va la maison.
auth-line-invitation = { $part ->
    [night] Bienvenue, même à cette heure.
    [evening] Bonsoir, et bienvenue.
   *[day] Bienvenue.
} Choisissez comment vous connecter : je vous reconnaîtrai ensuite.
auth-line-checking = Un instant, je cherche votre invitation.
auth-line-invalid = Je ne trouve pas cette invitation.
