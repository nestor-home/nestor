## Veilles : ce que l'assistant surveille pour le foyer.

watch-title = Veilles
watch-no-source = Aucune source disponible.
watch-no-source-hint = { $assistant } ne peut rien surveiller sans source : connectez un compte qui reçoit des mails, ou ajoutez des flux, des pages ou des webhooks aux sources entrantes.
watch-connect-account = connecter un compte
watch-add-source = ajouter une source
watch-active = Actives
watch-active-empty = Aucune veille active.
watch-active-empty-hint = Demandez-moi : « préviens-moi quand le colis arrive ».
watch-for = pour { $name }
watch-kind = { $kind ->
    [mail] mails
    [feed] flux
    [page] pages web
   *[other] { $kind }
}
watch-once = une seule fois
watch-every-time = à chaque fois
watch-triggered-count = { $count ->
    [one] 1 déclenchement
   *[other] { $count } déclenchements
}
watch-never-triggered = jamais déclenchée
watch-unknown = Cette veille n'existe pas ou a été annulée.
watch-cancelled-notice = D'accord, je ne surveille plus ça.
watch-created = créée { $when }
watch-until = jusqu'au { $when }
watch-cancel = Annuler la veille
watch-cancel-action = Annuler la veille…
watch-cancel-title = Annuler cette veille ?
watch-cancel-description = Plus rien ne sera signalé pour « { $what } ».
watch-found = Ce qu'elle a trouvé
watch-found-empty = Rien de pertinent pour l'instant.
watch-watches = surveille
watch-rhythm = fréquence
watch-rhythm-once = S'arrête au premier message trouvé.
watch-rhythm-every = Signale chaque message pertinent.
watch-asked-in = demandée dans
