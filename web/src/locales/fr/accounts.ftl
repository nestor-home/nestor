## Comptes d'administration, rôles et invitations.

acc-title = Comptes
acc-intro = Qui peut se connecter à l'admin, et avec quel rôle.
acc-invite = Inviter…
acc-invite-title = Inviter quelqu'un
acc-invite-description = Vous obtenez un lien à lui envoyer.
acc-invite-sent = { $has_person ->
    [yes] Envoyez ce lien à <strong>{ $person }</strong>. Valable une fois, pendant sept jours ; il ne sera plus affiché.
   *[no] Envoyez ce lien à la personne invitée. Valable une fois, pendant sept jours ; il ne sera plus affiché.
}
acc-invite-link = le lien d'invitation
acc-invite-done = Terminé
acc-role = Rôle
acc-person = Personne du foyer
acc-person-hint = Relie le compte à son journal et à ses connexions.
acc-person-none = Aucune
acc-person-none-lower = aucune
acc-inviting = Invitation…
acc-invite-create = Créer l'invitation
acc-last-owner = Il faut au moins un propriétaire actif.
acc-role-changed = { $name } est maintenant { $role }.
acc-disabled-done = Compte de { $name } désactivé.
acc-enabled-done = Compte de { $name } réactivé.
acc-you = vous
acc-disabled = désactivé
acc-active = actif
acc-never = jamais
acc-invitations-empty = Aucune invitation en attente.
acc-revoke = Retirer…
acc-revoke-title = Retirer cette invitation ?
acc-revoke-confirm = Retirer
acc-revoke-text = { $has_person ->
    [yes] Le lien créé pour { $person } cessera de fonctionner.
   *[no] Son lien cessera de fonctionner.
}
acc-not-found = Ce compte n'existe pas.
acc-field-person = personne
acc-field-created = créé
acc-field-seen = dernière connexion
acc-enable = Réactiver
acc-disable = Désactiver…
acc-disable-hint = Son journal, ses connexions et ses souvenirs sont conservés.
acc-disable-title = Désactiver le compte de { $name } ?
acc-disable-confirm = Désactiver
acc-disable-text = Il ne pourra plus se connecter. Vous pourrez le réactiver.
acc-people = Qui a accès
acc-invitations = Invitations en attente
acc-invitations-empty-hint = Une invitation est un lien valable une fois, pendant sept jours.
acc-invitation-anyone = Sans personne du foyer
acc-invitation-line = { $role } · expire { $expires }
acc-signin = Connexion
acc-disabled-note = Ce compte ne peut plus se connecter. Son journal, ses connexions et ses souvenirs sont conservés.
