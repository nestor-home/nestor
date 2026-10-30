## Comptes d'administration, rôles et invitations.

acc-title = Comptes
acc-intro = La reconnaissance d'une voix ou d'un visage ne remplace jamais un compte : les actions sensibles passent par ici.
acc-tab-accounts = Comptes
acc-tab-invitations = Invitations
acc-invite = Inviter…
acc-invite-title = Inviter quelqu'un
acc-invite-description = La personne reçoit un lien pour choisir son mot de passe.
acc-invite-sent = { $has_person ->
    [yes] Envoyez ce lien à <strong>{ $person }</strong> : il sert une seule fois, pendant sept jours, et ne sera plus affiché.
   *[no] Envoyez ce lien à la personne invitée : il sert une seule fois, pendant sept jours, et ne sera plus affiché.
}
acc-invite-link = le lien d'invitation
acc-invite-done = Terminé
acc-email = Adresse e-mail
acc-email-placeholder = odile@exemple.fr…
acc-role = Rôle
acc-role-of = Rôle de { $name }
acc-person = Personne du foyer
acc-person-hint = Relie le compte à son journal et à ses connexions.
acc-person-none = Aucune
acc-person-none-lower = aucune
acc-inviting = Invitation…
acc-invite-create = Créer l'invitation
acc-last-owner = Dernier propriétaire actif : le foyer doit en garder au moins un.
acc-role-changed = { $name } est maintenant { $role }.
acc-disabled-done = Compte de { $name } désactivé.
acc-enabled-done = Compte de { $name } réactivé.
acc-you = vous
acc-disabled = désactivé
acc-active = actif
acc-never-signed-in = jamais connecté
acc-never = jamais
acc-invitations-empty = Aucune invitation en attente.
acc-invitation-pending = [ en attente ] · { $role }{ $has_person ->
    [no] {""}
   *[yes] {" · "}{ $person }
} · expire { $expires }
acc-revoke = Retirer…
acc-revoke-title = Retirer cette invitation ?
acc-revoke-confirm = Retirer
acc-revoke-text = Le lien envoyé à { $email } cessera de fonctionner.
acc-not-found = Ce compte n'existe pas.
acc-field-person = personne
acc-field-created = créé
acc-field-seen = vu
acc-enable = Réactiver
acc-disable-section = Désactiver
acc-disable = Désactiver…
acc-disable-hint = Ses sessions sont fermées ; son journal, ses connexions et ses souvenirs restent.
acc-disable-title = Désactiver le compte de { $name } ?
acc-disable-confirm = Désactiver
acc-disable-text = Ses sessions sont fermées et il ne peut plus se connecter. Vous pourrez le réactiver.
