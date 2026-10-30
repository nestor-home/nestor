## Le journal : histoires (conversations, enchaînements, événements seuls), filtres, direct, tiroir.

jr-title = Journal
jr-loading = Chargement du journal…
jr-empty = Rien dans le journal pour ces filtres.
jr-empty-hint = Élargissez la période ou retirez un filtre.
jr-older = Plus ancien
jr-beginning = Début du journal
jr-now = maintenant
jr-paused = en pause
jr-new-events = { $count ->
    [one] 1 nouvel événement
   *[other] { $count } nouveaux événements
}
jr-story-count = { $count ->
    [one] 1 histoire
   *[other] { $count } histoires
}
jr-event-count = { $count ->
    [one] 1 événement
   *[other] { NUMBER($count) } événements
}
jr-day-list = Journal du { $day }

jr-search-label = Chercher dans le journal
jr-search-placeholder = Chercher : colis, facture, Jules…
jr-search-clear = Effacer la recherche
jr-range-hour = Dernière heure
jr-range-today = Aujourd'hui
jr-range-day = 24 dernières heures
jr-range-week = 7 derniers jours
jr-range-all = Toute la période
jr-range-since = Depuis { $from }
jr-range-until = Jusqu'à { $to }
jr-range-between = { $from } → { $to }
jr-density = Densité
jr-density-comfortable = Confortable
jr-density-compact = Compact
jr-pause = Pause
jr-resume = Reprendre
jr-pause-hint = Mettre le direct en pause (p)

jr-facet-kind = Type
jr-facet-person = Personne
jr-facet-channel = Canal
jr-facet-room = Pièce
jr-facet-clear = Effacer les filtres
jr-facet-search = Filtrer : { $facet }…
jr-facet-empty = Aucune valeur de ce nom.
jr-facet-selected = { $count } choisis

jr-histogram-label = { $count ->
    [one] 1 événement
   *[other] { $count } événements
} entre { $from } et { $to }

jr-story-thread = Conversation
jr-story-chain = Enchaînement
jr-story-single = Événement
jr-thread-title = { $count ->
    [0] Conversation
   *[other] Conversation · { $people }
}
jr-thread-open = Ouvrir cette conversation seule
jr-thread-link = fil
jr-thread-earlier = … début du fil sur une page plus ancienne
jr-entry-label = { $text } : { $detail }
jr-tool-count = { $count ->
    [one] 1 outil
   *[other] { $count } outils
}
jr-interrupted = interrompu
jr-call-details = Outil { $tool } : détails
jr-call-running = en cours
jr-call-ok = ok
jr-call-failed = échec
jr-call-arguments = arguments
jr-call-result = résultat
jr-chain-task = Tâche · { $what }
jr-chain-task-link = tâche
jr-chain-watch = Veille · { $what }
jr-chain-watch-link = veille
jr-chain-delivery = Prise de parole
jr-channel-voice = voix
jr-why = pourquoi

step-task-started = confiée
step-task-progressed = étape
step-task-completed = terminée
step-task-failed = en échec
step-watch-created = créée
step-watch-triggered = déclenchée
step-watch-triaged = triée
step-considered = décision
step-follow-up = relance
step-delivered-spoken = dit à voix haute
step-delivered-written = écrit
step-delivery-failed = non transmis

jr-event = Événement
jr-event-room = pièce « { $room } »
jr-related = Lié à
jr-related-person = Personne
jr-related-session = Conversation
jr-related-task = Tâche
jr-related-watch = Veille
jr-related-connection = Connexion
jr-related-satellite = Satellite
jr-related-memory = Souvenir
jr-related-cause = Causé par
jr-raw = Enregistrement brut
jr-raw-copy = l'enregistrement
jr-all-in-journal = tout dans le journal
jr-subject-session = Conversation
jr-subject-task = Tâche
jr-subject-watch = Veille
jr-subject-connection = Connexion
jr-subject-satellite = Satellite
jr-subject-tone = Ton
jr-subject-remove = Retirer le filtre { $subject } { $id }
jr-filters = Filtres
jr-filters-show = Afficher
jr-chip-remove = Retirer le filtre { $value }
jr-range-label = Période
