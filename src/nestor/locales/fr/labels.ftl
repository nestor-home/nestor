# Noms de ce que montre l'administration : rôles, permissions, statuts, risques, capacités.

role-name = { $role ->
    [owner] propriétaire
    [admin] administrateur
    [member] membre
    [guest] invité
   *[other] { $role }
}
scope-name = { $scope ->
    [accounts-manage] gérer les comptes
    [accounts-owners-manage] gérer les propriétaires
    [system-read] voir ce qui est branché
    [household-read] voir le foyer
    [household-connections-manage] gérer toutes les connexions
    [own-connections-manage] gérer ses propres connexions
    [satellites-manage] appairer les satellites
    [journal-read-all] lire tout le journal
    [journal-read-own] lire son propre journal
    [memory-manage-all] gérer tous les souvenirs
    [memory-manage-own] gérer ses propres souvenirs
    [tasks-manage] gérer toutes les tâches
    [tasks-manage-own] gérer ses propres tâches
    [watches-manage-all] gérer toutes les veilles
    [watches-manage-own] gérer ses propres veilles
   *[other] { $scope }
}
invitation-status = { $status ->
    [pending] en attente
    [accepted] acceptée
    [expired] expirée
    [revoked] retirée
   *[other] { $status }
}
task-status = { $status ->
    [running] en cours
    [completed] terminée
    [failed] en échec
    [cancelled] annulée
   *[other] { $status }
}
connection-status = { $status ->
    [connected] connectée
    [needs_reauth] à réautoriser
    [error] erreur
   *[other] { $status }
}
tool-risk = { $risk ->
    [read] lecture
    [write] écriture
    [sensitive] sensible
   *[other] { $risk }
}
auth-kind = { $auth ->
    [oauth2] OAuth
    [secret] identifiants
    [none] aucune
   *[other] { $auth }
}

capability-audio-capture = micro
capability-audio-playback = haut-parleur
capability-audio-speech_activity = détection de parole
capability-vision-person_detection = détection de personnes (sans image transmise)
capability-expression-emotion = expressions
capability-motion-head = mouvements de tête
