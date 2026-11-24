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
    [system-read] voir l'état du système
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
    [schedules-manage-all] gérer tous les rappels
    [schedules-manage-own] gérer ses propres rappels
    [messages-read-all] lire tous les messages et confirmations
    [messages-read-own] lire ses propres messages et confirmations
    [media-view] regarder les caméras qui lui sont ouvertes
    [media-view-all] regarder toutes les caméras
    [media-call] appeler par les satellites qui lui sont ouverts
    [media-call-all] appeler par tous les satellites
    [usage-read-all] voir ce que tout coûte
    [usage-read-own] voir ce que coûtent ses propres demandes
   *[other] { $scope }
}
invitation-status = { $status ->
    [pending] en attente
    [accepted] acceptée
    [expired] expirée
    [revoked] retirée
   *[other] { $status }
}
task-state = { $state ->
    [working] en cours
    [waiting] attend ta réponse
    [ready] prête
    [archived] archivée
   *[other] { $state }
}
turn-status = { $status ->
    [running] en cours
    [completed] revenue
    [asked] pose une question
    [failed] en échec
    [stopped] arrêtée
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
    [discovered] selon son serveur
   *[other] { $auth }
}

schedule-day = { $day ->
    [mon] lundi
    [tue] mardi
    [wed] mercredi
    [thu] jeudi
    [fri] vendredi
    [sat] samedi
   *[sun] dimanche
}
home-granularity = { $granularity ->
    [home] qui est à la maison
    [occupied_rooms] quelles pièces sont occupées
   *[person_room] qui est dans quelle pièce
}

capability-text-input = clavier
capability-text-display = texte à l’écran
capability-audio-capture = micro
capability-audio-playback = haut-parleur
capability-audio-speech_activity = détection de parole
capability-vision-person_detection = détection de personnes (sans image transmise)
capability-expression-emotion = expressions
capability-device-identify = identification (lumière, mouvement ou son)
capability-device-update = mises à jour à distance
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
pairing-method-enrollment-provisioning-hint = Donnez l'URI d'appairage à l'appareil (NESTOR_PAIRING_URI ou ses réglages).

# Pourquoi une connexion doit être réautorisée, ou est en erreur.
connection-refresh-refused = Accès révoqué ou expiré. Reconnectez le compte.
connection-no-refresh-token = Accès expiré, sans renouvellement possible. Reconnectez le compte.
connection-token-refused = Le service a refusé un accès tout juste renouvelé. Reconnectez le compte.

journal-kind = { $kind ->
    [conversation] Conversations
    [delivery] Prises de parole
    [tool] Outils
    [task] Tâches
    [watch] Veilles
    [schedule] Rappels
    [memory] Souvenirs
    [connection] Connexions
    [presence] Présence
    [satellite] Satellites
    [voice] Voix
    [observation] Observations
    [account] Comptes
    [usage] Coûts
   *[other] Autres
}

model-type = { $type ->
    [language] Modèles de langage (LLM)
    [embedding] Embeddings de texte
    [speaker] Reconnaissance du locuteur
    [transcription] Reconnaissance de la parole
    [speech] Synthèse vocale
    [image] Génération d'images
   *[other] Autres modèles
}
model-type-help = { $type ->
    [language] Pour répondre, à l'oral comme à l'écrit.
    [embedding] Pour retrouver souvenirs et conversations par le sens.
    [speaker] Pour savoir qui parle à un satellite.
    [transcription] Pour entendre ce qu'on dit à un satellite.
    [speech] Pour donner sa voix à l'assistant.
    [image] Pour dessiner les images qu'on demande.
   *[other] { "" }
}

usage-purpose = { $purpose ->
    [turn] réponses
    [notification] notifications
    [title] titres
    [watch] veilles
    [consolidation] mémoire
    [indexing] recherche dans la mémoire
    [enrollment] enregistrement de voix
    [task] tâches
    [search] recherche dans l’admin
    [unattributed] non attribué
   *[other] { $purpose }
}
usage-kind = { $kind ->
    [language] LLM
    [embedding] embedding
    [speaker] reconnaissance de voix
    [transcription] transcription
    [speech] synthèse vocale
    [image] images
   *[other] { $kind }
}
usage-basis = { $basis ->
    [reported] facturé
    [priced] estimé
    [free] gratuit
    [unknown] inconnu
    [nothing] rien facturé
   *[other] { $basis }
}
usage-outcome = { $outcome ->
    [ok] fait
    [failed] échoué
    [cancelled] interrompu
   *[other] { $outcome }
}
usage-dimension = { $dimension ->
    [consumer] modèle
    [kind] type
    [provider] fournisseur
    [served] modèle servi
    [purpose] usage
    [person] personne
    [channel] canal
    [medium] mode
    [basis] coût
    [outcome] issue
    [origin] origine
    [conversation] conversation
   *[other] { $dimension }
}
usage-unit = { $unit ->
    [input_tokens] tokens en entrée
    [cached_input_tokens] tokens en cache
    [cache_write_tokens] écritures en cache
    [output_tokens] tokens en sortie
    [images] images
    [audio_seconds] secondes entendues
    [characters] caractères prononcés
    [requests] appels
   *[other] { $unit }
}
