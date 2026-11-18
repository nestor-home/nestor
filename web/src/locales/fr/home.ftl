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
home-state-degraded = en mode dégradé

## Ce qu'il dit, à la première personne
home-say-delivered = Je viens de parler à { $people } ({ $where }).
home-say-listening = J'écoute { $people } ({ $where }).
home-say-answering = Je réponds à { $people }.
home-say-tool = Je consulte { $tool }.
home-say-presence-room = { $people } est dans « { $room } ».
home-say-presence-away = { $people } vient de partir.
home-say-memory = C'est noté, je m'en souviendrai.
home-say-working = { $count ->
    [one] Je travaille sur « { $objective } ».
   *[other] Je travaille sur « { $objective } » et { $others ->
        [one] une autre chose
       *[other] { $others } autres choses
    }.
}
home-say-concerned = { $count ->
    [one] J'ai besoin de vous pour une chose.
   *[other] J'ai besoin de vous pour { $count } choses.
}
home-say-sleeping = Heures calmes : je me tais jusqu'à { $until }.
home-say-idle = Tout est calme.

## Les colonnes
home-needs = Ce que j'attends de vous
home-room-nobody = personne
home-room-someone = quelqu'un
home-at-home = À la maison
home-away = Dehors
home-now = En ce moment
home-task-starting = démarrage
home-talking = Conversation avec { $people }
home-talking-someone = Conversation en cours
home-nothing-now = Rien en cours.
home-next = À venir
home-quiet-now = Silence jusqu'à { $until }, sauf urgence.
home-quiet-later = Heures calmes de { $from } à { $to }.
home-upcoming-unless = Sauf réponse d'ici là.

## Sa journée, ce qu'il sait
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

## La scène et ce qui s'ouvre depuis elle
today-so-far = Depuis ce matin
today-all-activity = Tout ce qui est en cours
today-nothing-next = Rien de prévu.
today-follow-up = Relance à { $person } sur { $channel }
today-follow-up-someone = Relance sur { $channel }
today-watching = { $count ->
    [one] Une veille active
   *[other] { $count } veilles actives
}
room-with = { $count ->
    [one] { $people } s'y trouve.
   *[other] { $people } s'y trouvent.
}
room-someone = Quelqu'un s'y trouve.
room-nobody = Personne en ce moment.
room-no-sensor = Aucun capteur ne dit s'il y a quelqu'un.
room-since = depuis
room-devices = Appareils
room-no-device = Aucun satellite dans cette pièce.
room-today = Aujourd'hui ici
room-quiet-today = Rien ne s'y est passé aujourd'hui.
today-needs-more = { $count ->
    [one] Voir une autre demande
   *[other] Voir { $count } autres demandes
}
today-needs-fewer = Réduire
today-rooms-more = { $count ->
    [one] Une autre pièce
   *[other] { $count } autres pièces
}
