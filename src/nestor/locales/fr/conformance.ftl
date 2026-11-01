# La suite de conformité des satellites (`nestor satellites conformance`) : ses vérifications, ce
# qu'elle a vu à la place, et les mots de la commande. Une vérification cite la règle de
# docs/satellite-protocol.md qu'elle prouve.

## Vérifications. `$connection` : paired (première connexion), reconnected, enrolled (appairé par code d'enrôlement).

conformance-asks-to-pair = demande à être appairé
conformance-declares-provisioning = déclare enrollment.provisioning (P1)
conformance-claims-token = récupère son jeton une fois son code d'appareil saisi (P2)
conformance-polls-after-identify = continue d'interroger après une identification en attente (I1)
conformance-connects = se connecte avec son jeton (W1)
conformance-reconnects = se reconnecte avec le même jeton après une coupure (W4)
conformance-connects-enrolled = se connecte après un appairage par code d'enrôlement
conformance-hello-first = { $connection ->
    [reconnected] après reconnexion : envoie d'abord un hello
    [enrolled] enrôlé : envoie d'abord un hello
   *[paired] envoie d'abord un hello
}
conformance-introduces = { $connection ->
    [reconnected] après reconnexion : se présente comme l'appareil appairé
    [enrolled] enrôlé : se présente comme l'appareil appairé
   *[paired] se présente comme l'appareil appairé
}
conformance-acknowledges = { $connection ->
    [reconnected] après reconnexion : acquitte { $intent } en { $seconds } s au plus
    [enrolled] enrôlé : acquitte { $intent } en { $seconds } s au plus
   *[paired] acquitte { $intent } en { $seconds } s au plus
}
conformance-follows-schema = { $connection ->
    [reconnected] après reconnexion : chaque message suit le schéma
    [enrolled] enrôlé : chaque message suit le schéma
   *[paired] chaque message suit le schéma
}
conformance-receives-audio = reçoit l'audio du cœur (W3)
conformance-sends-audio = envoie l'audio de son micro (W3)
conformance-enrolls = s'appaire avec le code d'enrôlement de { $variable }, sans code saisi (P3, P4)
conformance-falls-back = revient à un code d'appareil après le refus de son code d'enrôlement ({ $refusal ->
    [expired] expiré
    [used] déjà utilisé
   *[wrong] faux
}) (P5)
conformance-refused-once = ne présente qu'une fois un code d'enrôlement refusé ({ $refusal ->
    [expired] expiré
    [used] déjà utilisé
   *[wrong] faux
}) (P5)
conformance-waits-retry-after = attend Retry-After quand il est limité (P6)
conformance-pairs-after-limit = s'appaire une fois la limite levée (P6)
conformance-runs = tourne sans planter

## Ce qui a été vu à la place.

conformance-never-polled-after-identify = n'a plus interrogé après l'identification
conformance-no-offer = aucune offre authentifiée en { $seconds } s
conformance-first-message = premier message : { $type }
conformance-no-message = aucun message valide à temps
conformance-wrong-device = le hello dit { $said }, appairé comme { $paired }
conformance-no-ack = aucun acquittement portant l'identifiant de cette intention
conformance-off-schema = { $errors }
conformance-no-receiver-report = aucun rapport de réception RTCP du satellite
conformance-no-audio-frame = aucune trame audio du satellite
conformance-no-token = aucun jeton récupéré
conformance-no-code-sent = appairé sans présenter son code d'enrôlement
conformance-tries = { $count ->
    [one] une fois
   *[other] { $count } fois
}
conformance-attempts = tentatives à { $times } s
conformance-no-attempt = aucune tentative
conformance-raised = a levé { $error }
conformance-exited = terminé avec le code { $status }

## La commande.

conformance-help = vérifie un satellite selon nestor.satellite/2 (demande l'extra voice)
conformance-description = Vérifie un satellite, écrit dans n'importe quel langage, selon le standard nestor.satellite/2. Un faux cœur (le vrai service d'appairage et la vraie passerelle) lance la commande du satellite une fois par scénario : appairage par code d'appareil, par code d'enrôlement, codes refusés, limites de débit, identification, hello, acquittements, audio dans les deux sens et reconnexion.
conformance-epilog =
    Dans la commande, { "{url}" } est remplacé par l'URL du faux cœur et { "{state}" } par un dossier neuf pour le jeton du satellite.
    Les scénarios avec un code d'enrôlement le donnent dans la variable d'environnement NESTOR_PAIRING_URI (retirée dans les autres), comme une personne configure un appareil sans écran.
    Code de sortie : 0 si le satellite est conforme, 1 si une vérification échoue, 2 si la commande ne peut pas tourner.
conformance-deadline-help = secondes laissées au satellite pour chaque étape (par défaut : { $seconds })
conformance-command-help = la ligne de commande du satellite, après --
conformance-passed = OK     { $check }
conformance-failed = ÉCHEC  { $check }
conformance-failed-detail = ÉCHEC  { $check } ({ $detail })
conformance-conformant = conforme : { $total } vérifications passées
conformance-not-conformant = { $count ->
    [one] 1 vérification échouée
   *[other] { $count } vérifications échouées
} sur { $total }
conformance-no-command = nestor : donnez la commande du satellite après --, par exemple : nestor satellites conformance -- ./mon-satellite --core { "{url}" }
conformance-no-program = nestor : impossible de lancer { $program } (introuvable ou non exécutable)
conformance-needs-voice = nestor : la suite de conformité demande l'extra voice ({ $module } manque) : pip install 'nestor-home[voice]'
