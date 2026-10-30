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
    [config-manage] modifier la configuration et redémarrer
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
capability-device-identify = se signaler (lumière, mouvement ou son)
capability-motion-head = mouvements de tête

# Méthodes d'appairage (`pairing-method-<méthode, points en tirets>`), et ce que fait la personne.
pairing-method-device_code-display = Code sur son écran
pairing-method-device_code-display-hint = Saisissez le code affiché par l'appareil.
pairing-method-device_code-speech = Code dit à voix haute
pairing-method-device_code-speech-hint = Saisissez le code que dit l'appareil.
pairing-method-enrollment-qr = QR code
pairing-method-enrollment-qr-hint = Montrez le QR code à la caméra de l'appareil.
pairing-method-enrollment-input = Code saisi sur l'appareil
pairing-method-enrollment-input-hint = Saisissez ce code sur l'appareil.
pairing-method-enrollment-provisioning = Configuration
pairing-method-enrollment-provisioning-hint = Donnez à l'appareil l'adresse d'appairage, dans NESTOR_PAIRING_URI ou ses réglages.

# Pourquoi une connexion doit être réautorisée, ou est en erreur.
connection-refresh-refused = Le service a refusé de renouveler l'accès : il a été révoqué ou a expiré. Reconnectez le compte.
connection-no-refresh-token = L'accès a expiré et le service n'a donné aucun moyen de le renouveler. Reconnectez le compte.
connection-reason-other = { $detail }
