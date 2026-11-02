# La suite de conformité des satellites (`nestor satellites conformance`) : ses vérifications, ce
# qu'elle a vu à la place, et les mots de la commande. Une vérification cite la règle du standard
# (https://nestorhome.dev/fr/docs/satellites/protocol/) qu'elle prouve.

## Vérifications. `$connection` : paired (première connexion), reconnected, enrolled (appairé par code d'enrôlement).

conformance-asks-to-pair = demande à être appairé
conformance-declares-provisioning = déclare enrollment.provisioning (P1)
conformance-claims-token = récupère son jeton une fois son code d'appareil saisi (P2)
conformance-polls-after-identify = continue d'interroger après une identification en attente (I1)
conformance-connects = ouvre son lien avec son jeton, un hello d'abord, comme l'appareil appairé (L1)
conformance-reconnects = se reconnecte avec le même jeton quand le cœur ferme son lien (L5)
conformance-connects-enrolled = ouvre son lien après un appairage par code d'enrôlement
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
conformance-exchanges-audio = échange de l'audio, comme autorisé (A1, A2)
conformance-receives-audio = reçoit l'audio du cœur (A1, A2)
conformance-sends-audio = envoie l'audio de son micro (A1, A2)
conformance-pairs-again = oublie un jeton refusé et s'appaire à nouveau (L2, P8)
conformance-no-unallowed-audio = ne propose pas d'audio quand l'audio n'est pas autorisé (A1)
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
conformance-no-link = aucun lien en { $seconds } s
conformance-link-refused = lien fermé avec { $code } : { $why }
conformance-no-audio-offer = aucune offre audio en { $seconds } s
conformance-voice-missing = l'audio ne se vérifie pas sans l'extra voice ({ $module } manque)
conformance-audio-offers = { $count ->
    [one] 1 offre audio
   *[other] { $count } offres audio
}
conformance-never-asked-again = n'a jamais redemandé à s'appairer
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

conformance-help = vérifie un satellite selon nestor.satellite/1 (l'audio demande l'extra voice)
conformance-description = Vérifie un satellite, écrit dans n'importe quel langage, selon le standard nestor.satellite/1. Un faux cœur (le vrai service d'appairage et la vraie passerelle) lance la commande du satellite une fois par scénario : appairage par code d'appareil, par code d'enrôlement, codes refusés, limites de débit, identification, le lien et son hello, acquittements, texte, audio dans les deux sens s'il est autorisé, reconnexion et jeton refusé.
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
