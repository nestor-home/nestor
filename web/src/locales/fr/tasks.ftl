## Tâches : le travail confié aux exécutants, chacune un fil de tours auquel on peut répondre, qu'on peut réorienter ou relancer.

task-running-empty-hint = Confiez-moi quelque chose de long : comparer des offres, préparer un dossier.
task-unknown = Cette tâche n'existe pas, ou vous ne pouvez pas la voir.
task-starting = Démarrage…
task-turns = { $count ->
    [one] { $count } tour
   *[other] { $count } tours
}
task-for = pour { $name }
task-thread = Fil
task-notes = Notes
task-story = Déroulé
task-story-empty = Aucune trace dans le journal.
task-about = À propos de cette tâche
task-about-state = État
task-asked-by = Demandée par
task-asked-in = Demandée dans
task-done-by = Confiée à
task-started = Ouverte
task-steered = donnée pendant le travail
task-turn-stopped = Arrêtée avant d'avoir rendu quoi que ce soit.
task-turn-empty = Revenue sans compte rendu.
task-delivered = { $spoken ->
    [yes] Dit à voix haute
   *[no] Écrit sur { $channel }
}{ $room ->
    [none] {""}
   *[other] , dans « { $room } »
},
task-composer-steer = Réorienter le travail en cours…
task-composer-steer-hint = Prise en compte dans le tour en cours.
task-composer-restart = Donner une nouvelle consigne…
task-composer-restart-hint = Arrête le tour en cours et en lance un nouveau avec elle.
task-composer-answer = Répondre à sa question…
task-composer-answer-hint = Votre réponse lance son tour suivant.
task-composer-continue = Demander une suite…
task-composer-continue-hint = Lance un nouveau tour dans le même fil.
task-composer-reopen = Demander une suite…
task-composer-reopen-hint = Lui écrire la sort des archives.
task-send = Envoyer
task-steered-notice = Pris en compte dans le travail en cours.
task-continued-notice = Envoyé : la tâche reprend.
task-write-steer = Réorienter…
task-write-steer-title = Réorienter le travail en cours
task-write-restart = Nouvelle consigne…
task-write-restart-title = Donner une nouvelle consigne
task-write-answer = Répondre…
task-write-answer-title = Répondre à la tâche
task-write-continue = Relancer…
task-write-continue-title = Demander une suite
task-write-reopen = Relancer…
task-write-reopen-title = Demander une suite
task-rename-action = Renommer…
task-rename-title = Renommer la tâche
task-rename-label = Titre
task-rename-save = Renommer
task-renamed-notice = Renommée.
task-stop = Arrêter
task-stop-action = Arrêter…
task-stop-title = Arrêter le travail en cours ?
task-stop-description = La tâche reste : vous pourrez lui donner une nouvelle consigne plus tard.
task-stopped-notice = Arrêtée.
task-stop-pending-notice = Arrêt demandé : l'exécutant ne l'a pas encore confirmé.
task-archive = Archiver
task-archive-action = Archiver…
task-archive-title = Archiver cette tâche ?
task-archive-description = { $working ->
    [yes] Le travail en cours s'arrête d'abord. Lui écrire plus tard la sort des archives.
   *[no] Lui écrire plus tard la sort des archives.
}
task-archived-notice = Archivée.
