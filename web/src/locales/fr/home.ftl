## Aujourd'hui : la vue d'ensemble de la journée du foyer.

home-greeting-night = Bonne nuit
home-greeting-day = Bonjour
home-greeting-evening = Bonsoir
home-hello = { $greeting }, { $name }.
home-summary = Aujourd'hui, { $assistant } a tenu <b>{ $conversations ->
    [0] aucune conversation
    [one] 1 conversation
   *[other] { $conversations } conversations
}</b>, appelé <b>{ $tools ->
    [0] aucun outil
    [one] 1 outil
   *[other] { $tools } outils
}</b> et pris la parole <b>{ $spoken ->
    [one] une fois
   *[other] { $spoken } fois
}</b>.
home-running = { $count ->
    [one] 1 tâche tourne en ce moment.
   *[other] { $count } tâches tournent en ce moment.
}
home-attention = { $count ->
    [one] 1 chose demande votre attention.
   *[other] { $count } choses demandent votre attention.
}
home-all-good = Rien ne demande votre attention.
home-activity = activité du jour
home-attention-title = À regarder
home-attention-empty = Tout fonctionne : aucune connexion à réautoriser, aucun appareil en attente, aucun message perdu.
home-at-home = À la maison
home-presence-home = à la maison
home-presence-away = pas à la maison
home-presence-unknown = présence inconnue
home-now = En ce moment
home-now-tasks = tâches
home-now-watches = veilles
home-now-satellites = satellites
home-task-starting = démarrage
home-no-task = Aucune tâche en cours.
home-watch-triggered = déclenchée
home-watch-never = pas encore déclenchée
home-deliveries = Prises de parole du jour
home-all-journal = tout le journal
home-deliveries-empty = Pas encore de prise de parole aujourd'hui.
home-deliveries-empty-hint = Il parle de lui-même quand une tâche se termine ou qu'une veille trouve quelque chose.
home-delivered-spoken = à voix haute
home-delivered-written = par écrit sur { $channel }
