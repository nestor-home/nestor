## Aujourd'hui : l'agent en ce moment — ce qu'il perçoit, fait, compte faire, a fait et sait.

home-greeting-night = Bonne nuit
home-greeting-day = Bonjour
home-greeting-evening = Bonsoir
home-hello = { $greeting }, { $name }.
home-today = aujourd'hui · { $conversations ->
    [0] aucune conversation
    [one] 1 conversation
   *[other] { $conversations } conversations
} · { $spoken ->
    [0] aucune prise de parole
    [one] 1 prise de parole
   *[other] { $spoken } prises de parole
}

## La carte
home-mind-title = Ce que { $agent } perçoit en ce moment
home-mind-core = { $agent }, { $state } : voir le journal
home-mind-house = la maison
home-mind-reach = ce qu'il atteint
home-state-listening = à l'écoute
home-state-thinking = réfléchit
home-state-speaking = parle
home-state-working = travaille
home-state-idle = au repos
home-state-laughing = rit
home-state-concerned = préoccupé
home-state-sleeping = en veille
home-say-delivered = Je viens de parler à { $people } · { $where }.
home-say-listening = J'écoute { $people } · { $where }.
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
home-state-degraded = fonctionne en mode dégradé
home-room-label = { $room } : { $people } ; { $devices ->
    [0] aucun appareil
    [one] 1 appareil
   *[other] { $devices } appareils
}. Voir ce qui s'y est passé.
home-room-nobody = personne
home-away = hors de la maison
home-away-label = Hors de la maison : { $names }
home-channels = Canaux
home-channels-label = Canaux : { $names }
home-task-label = Tâche : { $objective }, { $steps ->
    [one] 1 étape
   *[other] { $steps } étapes
}
home-task-steps = { $count ->
    [0] démarre
    [one] 1 étape
   *[other] { $count } étapes
}
home-watches = { $count ->
    [one] 1 veille
   *[other] { $count } veilles
}
home-watches-label = { $count ->
    [one] 1 veille active
   *[other] { $count } veilles actives
}
home-connections = { $count ->
    [one] 1 connexion
   *[other] { $count } connexions
}
home-connections-label = { $count ->
    [one] 1 connexion
   *[other] { $count } connexions
}{ $troubled ->
    [0] , toutes en état
    [one] , dont 1 à regarder
   *[other] , dont { $troubled } à regarder
}

## Ce qu'il fait, ce qu'il compte faire
home-doing = Ce qu'il fait, ce qu'il compte faire
home-now = maintenant
home-next = ensuite
home-task-starting = démarrage
home-talking = Conversation avec { $people } · { $where }
home-talking-someone = Conversation en cours · { $where }
home-nothing-now = Rien en cours : il attend qu'on lui parle.
home-quiet-now = Silence jusqu'à { $until } : rien ne sera dit à voix haute, sauf urgence.
home-quiet-later = Heures calmes de { $from } à { $to }.
home-main-room = pièce principale : { $room }
home-watch-triggered = déclenchée
home-watch-waiting = attend sur { $sources }
home-nothing-next = Rien de prévu.

## Sa journée
home-day = Sa journée
home-all-journal = tout le journal
home-day-marks = { $count ->
    [0] Rien encore aujourd'hui
    [one] 1 moment aujourd'hui
   *[other] { $count } moments aujourd'hui
}
home-mark-conversation = { $time } : conversation avec { $people } ({ $count ->
    [one] 1 tour
   *[other] { $count } tours
})
home-mark-delivery = { $time } : a parlé à { $people } ({ $where })
home-mark-task = { $time } : tâche confiée
home-mark-watch = { $time } : une veille s'est déclenchée
home-mark-memory = { $time } : a retenu quelque chose
home-mark-problem = { $time } : un échec
home-legend-conversation = { $count } conversations
home-legend-delivery = { $count } prises de parole
home-legend-task = { $count } tâches
home-legend-watch = { $count } veilles déclenchées
home-legend-memory = { $count } souvenirs
home-legend-problem = { $count } échecs
home-legend-quiet = heures calmes

## Ce qui demande ton attention, ce qu'il sait
home-attention-title = Ce qui demande votre attention
home-knows = Ce qu'il sait
home-all-memories = tous les souvenirs
home-learnt-today = appris aujourd'hui à { $time }
