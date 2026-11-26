## Alertes : ce que l'assistant fait plus tard, régulièrement, ou quand quelque chose arrive.

alert-empty-hint = Demandez à { $assistant } : « rappelle-moi demain à 9 h d'appeler le plombier », « préviens-moi quand le colis arrive », « dis-moi dès que l'action passe sous 135 ».
alert-for = pour { $name }
alert-kind = { $kind ->
    [mail] mails
    [feed] flux
    [page] pages web
   *[other] { $kind }
}
alert-once-at = Une fois, { $when }
alert-every-day = tous les jours
alert-on-kinds = À l'arrivée de { $kinds }
alert-rang-count = { $count ->
    [one] A sonné une fois
   *[other] A sonné { $count } fois
}
alert-never-rang = N'a pas encore sonné
alert-unknown = Cette alerte n'existe pas ou est terminée.
alert-cancelled-notice = Annulée : elle ne sonnera plus.
alert-created = créée { $when }
alert-until = jusqu'au { $when }
alert-cancel = Annuler l'alerte
alert-cancel-action = Annuler l'alerte…
alert-cancel-title = Annuler cette alerte ?
alert-cancel-description = « { $what } » ne sonnera plus.
alert-trigger = Sonne
alert-condition = Seulement si :
alert-frequency-term = Fréquence
alert-urgent = Urgente : dite tout de suite, même aux heures calmes
alert-so-far = Jusqu'ici
alert-rings = Pourquoi elle a sonné
alert-rings-empty = Elle n'a pas encore sonné.
alert-last-rang = A sonné
alert-found = Son déroulé
alert-found-empty = Rien pour l'instant.
alert-asked-in = Demandée dans
