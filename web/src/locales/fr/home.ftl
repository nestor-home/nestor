## Aujourd'hui : l'agent en ce moment, ce qu'il perçoit, fait, compte faire, a fait et sait.

home-greeting-night = Bonne nuit
home-greeting-day = Bonjour
home-greeting-evening = Bonsoir
home-hello = { $greeting }, { $name }.
home-figure-label = { $agent }, { $state }. Voir le journal.

## Ce qu'il est en train de faire
home-state-listening = à l'écoute
home-state-thinking = réfléchit
home-state-speaking = parle
home-state-laughing = rit
home-state-working = travaille
home-state-concerned = préoccupé
home-state-sleeping = en veille
home-state-idle = disponible
home-state-degraded = fonctionne en mode dégradé

## Ce qu'il dit, à la première personne
home-say-delivered = Je viens de parler à { $people } ({ $where }).
home-say-listening = J'écoute { $people } ({ $where }).
home-say-answering = Je réponds à { $people }.
home-say-tool = Je consulte { $tool }.
home-say-presence-room = { $people } est au { $room }.
home-say-presence-away = { $people } vient de partir.
home-say-memory = C'est noté, je m'en souviendrai.
home-say-working = { $count ->
    [one] Je travaille sur « { $objective } ».
   *[other] Je travaille sur « { $objective } » et { $others ->
        [one] une autre chose
       *[other] { $others } autres choses
    }.
}
home-say-concerned = { $count ->
    [one] J'ai besoin de vous pour une chose.
   *[other] J'ai besoin de vous pour { $count } choses.
}
home-say-sleeping = Heures calmes : je me tais jusqu'à { $until }.
home-say-idle = Tout est calme. Je suis là si besoin.

## Les colonnes
home-needs = Ce que j'attends de vous
home-house = La maison
home-room-nobody = personne
home-room-offline = { $count ->
    [one] appareil hors ligne
   *[other] { $count } appareils hors ligne
}
home-away = Dehors
home-now = En ce moment
home-task-starting = démarrage
home-talking = Conversation avec { $people }
home-talking-someone = Conversation en cours
home-nothing-now = Rien en cours. J'attends qu'on me parle.
home-next = À venir
home-quiet-now = Silence jusqu'à { $until }, sauf urgence.
home-quiet-later = Heures calmes de { $from } à { $to }.
home-upcoming = Je l'écrirai à { $person } sur { $channel } à { $time }.
home-upcoming-someone = Je l'écrirai sur { $channel } à { $time }.
home-upcoming-unless = Sauf si quelqu'un répond d'ici là.
home-watch-triggered = déclenchée

## Sa journée, ce qu'il sait
home-today = Aujourd'hui
home-today-empty = Rien encore aujourd'hui.
home-moment-conversation = Conversation avec { $people } ({ $count ->
    [one] 1 tour
   *[other] { $count } tours
})
home-moment-conversation-someone = Conversation ({ $count ->
    [one] 1 tour
   *[other] { $count } tours
})
home-all-journal = Tout le journal
home-knows = Ce que je sais
home-all-memories = Tous les souvenirs
home-learnt-today = appris aujourd'hui à { $time }
