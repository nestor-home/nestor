# Le journal de l'administration : une phrase par événement (`journal-*`), son détail et sa catégorie.

journal-other = { $type }
journal-kind = { $kind ->
    [conversation] Conversations
    [delivery] Prises de parole
    [tool] Outils
    [task] Tâches
    [watch] Veilles
    [memory] Souvenirs
    [connection] Connexions
    [presence] Présence
    [satellite] Satellites
    [observation] Observations
    [account] Comptes
   *[other] Autres
}

journal-user-said = { $known ->
    [no] Quelqu'un a dit
   *[yes] { $person } a dit
}
journal-assistant-answered = { $assistant } a répondu
journal-assistant-interrupted = { $assistant } a répondu (interrompu)
journal-fallback = Réponse de secours : { $reason ->
    [model_unavailable] modèle indisponible
    [model_slow] modèle trop lent
    [recognition_unavailable] reconnaissance vocale indisponible
    [synthesis_unavailable] synthèse vocale indisponible
   *[other] { $reason }
}
journal-answer-cut = Réponse coupée par la personne
journal-detail-heard = Entendu : { $heard }

journal-tool-called = Outil { $tool } appelé
journal-tool-completed = Outil { $tool } terminé en { NUMBER($seconds, maximumFractionDigits: 1) } s
journal-tool-failed = Outil { $tool } en échec

journal-task-started = Tâche { $task } confiée à { $executor }
journal-task-attached = Tâche { $task } suivie chez l'exécutant
journal-task-progressed = Tâche { $task } : nouvelle étape
journal-task-cancel-requested = Arrêt demandé pour la tâche { $task }
journal-task-ended = Tâche { $task } { $status ->
    [completed] terminée
    [failed] en échec
    [cancelled] annulée
   *[other] { $status }
} ({ NUMBER($seconds, maximumFractionDigits: 0) } s)
journal-task-delivered = Résultat de la tâche { $task } transmis

journal-delivery-considered = { $known ->
    [no] Décision de parler
   *[yes] Décision de parler à { $person }
} : { $subject ->
    [task] tâche { $id } { $status ->
        [completed] terminée
        [failed] en échec
        [cancelled] annulée
       *[other] { $status }
    }
    [watch] veille { $id }
   *[other] { $about }
}{ $follow_up ->
    [yes] {" "}(relance)
   *[no] {""}
}
journal-delivered = Message transmis : { $subject ->
    [task] tâche { $id } { $status ->
        [completed] terminée
        [failed] en échec
        [cancelled] annulée
       *[other] { $status }
    }
    [watch] veille { $id }
   *[other] { $about }
}{ $follow_up ->
    [yes] {" "}(relance)
   *[no] {""}
}
journal-delivery-failed = Message non transmis : { $subject ->
    [task] tâche { $id } { $status ->
        [completed] terminée
        [failed] en échec
        [cancelled] annulée
       *[other] { $status }
    }
    [watch] veille { $id }
   *[other] { $about }
}{ $follow_up ->
    [yes] {" "}(relance)
   *[no] {""}
}
journal-detail-plan = Prévu : { $way ->
    [spoken] à voix haute sur { $spoken }
    [written] par écrit sur { $written }
    [both] à voix haute sur { $spoken } puis par écrit sur { $written }
   *[none] nulle part
}
journal-detail-tried = { $count ->
    [0] Essayé : aucun canal disponible
   *[other] Essayé : { $tried }
}

journal-watch-created = Veille créée : { $what }
journal-detail-keywords = Mots-clés : { $keywords }
journal-watch-triggered = { $urgent ->
    [yes] Veille { $watch } déclenchée par « { $item } » (urgent)
   *[no] Veille { $watch } déclenchée par « { $item } »
}
journal-watch-ended = Veille { $watch } { $reason ->
    [matched] trouvée
    [expired] expirée
    [cancelled] annulée
   *[other] { $reason }
}

journal-memory-recorded = Souvenir enregistré
journal-memory-corrected = Souvenir corrigé
journal-memory-forgotten = Souvenir oublié

journal-connection-created = Compte { $account } connecté ({ $kind })
journal-connection-changed = Connexion { $connection } { $status ->
    [connected] connectée
    [needs_reauth] à réautoriser
    [error] en erreur
   *[other] { $status }
}
journal-connection-removed = Connexion { $connection } supprimée

journal-presence-changed = { $where ->
    [away] { $person } n'est plus à la maison
    [room] { $person } est dans la pièce « { $room } »
    [home] { $person } est à la maison
   *[unknown] { $person } n'est plus localisé·e
}

journal-satellite-pairing-requested = Le satellite { $device } ({ $model }, pièce « { $room } ») demande l'appairage
journal-detail-declares = { $count ->
    [0] Déclare : rien
   *[other] Déclare : { $capabilities }
}
journal-satellite-paired = { $proof ->
    [enrollment_code] Satellite { $device } appairé avec un code d'ajout (pièce « { $room } »)
   *[device_code] Satellite { $device } appairé avec son code (pièce « { $room } »)
}
journal-detail-allowed = { $count ->
    [0] Autorisé : rien
   *[other] Autorisé : { $capabilities }
}
journal-satellite-revoked = Satellite { $device } révoqué
journal-satellite-connected = Satellite { $device } connecté (pièce « { $room } »)
journal-satellite-disconnected = Satellite { $device } déconnecté (pièce « { $room } »)
journal-satellite-addition-started = { $proof ->
    [enrollment_code] Code d'ajout créé pour un satellite
   *[device_code] Ajout d'un satellite par le code qu'il présente
}
journal-satellite-addition-completed = Satellite { $device } ajouté
journal-satellite-addition-cancelled = Ajout de satellite annulé
journal-satellite-addition-expired = Ajout de satellite expiré sans servir
journal-satellite-enrollment-refused = { $reason ->
    [expired] { $device } a présenté un code d'ajout expiré
    [used] { $device } a présenté un code d'ajout déjà utilisé
    [cancelled] { $device } a présenté un code d'ajout annulé
   *[unknown] { $device } a présenté un mauvais code d'ajout
}
journal-satellite-identify-requested = { $device } invité à se signaler
journal-person-detected = { $count ->
    [one] { $count } personne vue par { $device } (pièce « { $room } »)
   *[other] { $count } personnes vues par { $device } (pièce « { $room } »)
}
journal-detail-confidence = Confiance : { NUMBER($confidence, style: "percent") }
journal-speech-activity = { $active ->
    [yes] Parole détectée près de { $device } (pièce « { $room } »)
   *[no] Fin de parole près de { $device } (pièce « { $room } »)
}

journal-account-created = Compte { $login } ouvert ({ role-name })
journal-account-role-changed = Compte { $login } : rôle { role-name }
journal-account-disabled = Compte { $login } désactivé
journal-account-enabled = Compte { $login } réactivé
journal-account-password-changed = Mot de passe du compte { $login } changé
journal-account-locale-changed = { $chosen ->
    [no] Le compte { $login } lit désormais dans la langue du foyer
   *[yes] Le compte { $login } lit désormais en { $locale }
}
journal-account-invited = { $known ->
    [no] Invitation ({ role-name })
   *[yes] Invitation ({ role-name }) pour { $person }
}
journal-invitation-revoked = Invitation { $invitation } retirée
journal-login-succeeded = Connexion de { $login }
journal-login-failed = { $known ->
    [no] Connexion refusée : { $reason ->
        [wrong-password] mot de passe incorrect
        [unknown-login] identifiant inconnu
        [disabled] compte désactivé
       *[other] { $reason }
    }
   *[yes] Connexion refusée au compte { $login } : { $reason ->
        [wrong-password] mot de passe incorrect
        [unknown-login] identifiant inconnu
        [disabled] compte désactivé
       *[other] { $reason }
    }
}

journal-observation-speaker-identified = { $known ->
    [no] Voix non reconnue
   *[yes] Voix de { $person } reconnue
}
journal-identity-enrolled = Empreinte vocale enregistrée pour { $person }
journal-identity-forgotten = Empreinte vocale de { $person } supprimée

journal-behavior-changed = Attitude : { $behavior ->
    [idle] au repos
    [listening] à l'écoute
    [thinking] réfléchit
    [speaking] parle
   *[other] { $behavior }
}
journal-expression-requested = Expression : { $expression ->
    [joy] joie
    [sigh] soupir
    [thoughtful] pensif
    [whisper] chuchotement
    [excited] enthousiasme
    [ahem] raclement de gorge
   *[other] { $expression }
}

journal-config-changed = { $restored ->
    [yes] Configuration précédente restaurée { $via ->
        [cli] depuis la ligne de commande
       *[admin] par { $login }
    }
   *[no] Configuration modifiée { $via ->
        [cli] depuis la ligne de commande
       *[admin] par { $login }
    }
}
journal-detail-settings = { $count ->
    [one] Réglage : { $paths }
   *[other] Réglages : { $paths }
}
journal-secret-changed = { $removed ->
    [yes] Secret { $name } supprimé
   *[no] Secret { $name } enregistré
} { $via ->
    [cli] depuis la ligne de commande
   *[admin] par { $login }
}
journal-system-restart-requested = Redémarrage demandé { $via ->
    [cli] depuis la ligne de commande
   *[admin] par { $login }
}
