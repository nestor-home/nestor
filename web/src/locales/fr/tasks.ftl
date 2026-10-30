## Tâches : le travail long confié aux exécutants, de la demande à la remise.

task-title = Tâches
task-intro = Le travail long confié aux exécutants, du moment où il a été demandé à sa remise.
task-running = En cours
task-running-empty = Aucune tâche en cours.
task-running-empty-hint = Demandez-lui quelque chose de long : comparer des offres, préparer un dossier.
task-done = Terminées
task-done-empty = Aucune tâche terminée.
task-for = pour { $name }
task-since = depuis
task-unknown = Cette tâche n'existe pas ou plus.
task-requested-by = demandée par { $name }
task-took = durée { $duration }
task-cancel = Arrêter
task-cancel-action = Arrêter…
task-cancel-title = Arrêter cette tâche ?
task-cancel-description = L'exécutant reçoit l'ordre d'arrêter ; ce qui est déjà fait le reste.
task-cancel-notice = Arrêt demandé pour la tâche { $id }.
task-story = Déroulé
task-story-empty = Le journal ne garde aucune trace de cette tâche.
task-error = erreur
task-result = résultat
task-asked-in = demandée dans
task-a-conversation = une conversation
task-conversation-older = une conversation plus ancienne que le journal
task-delivery = remise
task-delivered = { $spoken ->
    [yes] Dite à voix haute
   *[no] Écrite sur { $channel }
}{ $room ->
    [none] {""}
   *[other] , pièce « { $room } »
},
task-delivery-pending = À la fin, le résultat sera dit à la personne là où elle se trouve.
task-delivery-none = Pas de remise.
