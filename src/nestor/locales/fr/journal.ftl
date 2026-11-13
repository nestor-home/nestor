# Le journal de l'administration : une phrase par événement (`journal-*`), son détail et sa catégorie.

journal-other = { $type }

journal-user-said = { $known ->
    [no] Quelqu'un a dit
   *[yes] { $by ->
        [voice] { $person } a dit (voix reconnue)
        [said] { $person } a dit (nom annoncé)
       *[other] { $person } a dit
    }
}
journal-notification-turn = Pour { $assistant } : { journal-subject }
journal-assistant-answered = { $assistant } a répondu
journal-assistant-interrupted = { $assistant } a répondu (interrompu)
journal-fallback = Réponse de secours : { $reason ->
    [model_unavailable] modèle indisponible
    [model_slow] modèle trop lent
    [recognition_unavailable] reconnaissance vocale indisponible
    [synthesis_unavailable] synthèse vocale indisponible
   *[other] { $reason }
}
journal-answer-cut = Réponse interrompue
journal-model-fell-back = { $model } a échoué : { $fallback } prend le relais
journal-conversation-titled = Conversation intitulée « { $title } »
journal-answer-voiced = { $assistant } a répondu par un message vocal
journal-answer-files = { $count ->
    [one] { $assistant } a joint un fichier à sa réponse
   *[other] { $assistant } a joint { $count } fichiers à sa réponse
}
journal-detail-heard = Entendu : { $heard }

journal-tool-called = Outil { $tool } appelé
journal-tool-completed = Outil { $tool } terminé en { NUMBER($seconds, maximumFractionDigits: 1) } s
journal-tool-failed = Outil { $tool } en échec
journal-tool-deferred = Outil { $tool } toujours en cours : son résultat reviendra
journal-tool-returned = Outil { $tool } a répondu après { NUMBER($seconds, maximumFractionDigits: 0) } s
journal-tool-returned-failed = Outil { $tool } en échec après { NUMBER($seconds, maximumFractionDigits: 0) } s
journal-tool-result-stored = Résultat long mis de côté ({ NUMBER($size) } caractères)
journal-tool-result-delivered = Résultat de l'outil { $tool } transmis

journal-task-started = Tâche { $task } confiée à { $executor }
journal-task-attached = Tâche { $task } prise en charge par l'exécutant
journal-task-progressed = Tâche { $task } : nouvelle étape
journal-task-cancel-requested = Annulation demandée pour la tâche { $task }
journal-task-ended = Tâche { $task } { $status ->
    [completed] terminée
    [failed] en échec
    [cancelled] annulée
   *[other] { $status }
} ({ NUMBER($seconds, maximumFractionDigits: 0) } s)
journal-task-delivered = Résultat de la tâche { $task } transmis

journal-subject = { $subject ->
    [task] tâche { $id } { $status ->
        [completed] terminée
        [failed] en échec
        [cancelled] annulée
       *[other] { $status }
    }
    [watch] veille { $id }
    [schedule] rappel { $id }
    [tool] résultat d'un outil{ $status ->
        [failed] {" "}(en échec)
       *[other] {""}
    }
    [message] message { $id }{ $status ->
        [undelivered] {" "}non remis
       *[other] {""}
    }
   *[confirmation] confirmation { $id }{ $status ->
        [done] {" "}exécutée
       *[other] {""}
    }
}{ $follow_up ->
    [yes] {" "}(relance)
   *[no] {""}
}
journal-delivery-considered = { $known ->
    [no] Message
   *[yes] Message pour { $person }
} : { journal-subject }
journal-delivered = Message transmis : { journal-subject }
journal-delivery-withheld = Rien à dire : { journal-subject }
journal-message-requested = { $kind ->
    [question] Question de { $by } pour { $to }
    [answer] Réponse de { $by } pour { $to }
   *[other] Message de { $by } pour { $to }
}
journal-message-delivered = Message { $id } remis
journal-message-undelivered = Message { $id } non remis
journal-delivery-failed = Message non transmis : { journal-subject }
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

journal-schedule-created = { $recurring ->
    [yes] Réveil régulier programmé
   *[no] Réveil programmé
}
journal-schedule-fired = Réveil { $id } déclenché
journal-schedule-cancelled = Réveil { $id } annulé
journal-watch-created = Veille créée : { $what }
journal-watch-sorted = { $unsorted ->
    [yes] « { $item } » non trié : le modèle n'a pas répondu
   *[no] { $matched ->
        [0] « { $item } » vérifié pour { $asked } { $asked ->
            [one] veille
           *[other] veilles
        } : aucune ne correspond
       *[other] « { $item } » vérifié pour { $asked } { $asked ->
            [one] veille
           *[other] veilles
        } : { $matched } { $matched ->
            [one] correspond
           *[other] correspondent
        }
    }
}
journal-watch-triggered = { $urgent ->
    [yes] Veille { $watch } déclenchée par « { $item } » (urgent)
   *[no] Veille { $watch } déclenchée par « { $item } »
}
journal-watch-ended = Veille { $watch } { $reason ->
    [matched] déclenchée
    [expired] expirée
    [cancelled] annulée
   *[other] { $reason }
}

journal-memory-recorded = { $drawn ->
    [yes] Souvenir tiré d'une conversation
   *[no] Souvenir enregistré
}
journal-memory-corrected = Souvenir corrigé
journal-memory-forgotten = Souvenir oublié
journal-episode-summarized = { $kept ->
    [yes] Conversation résumée
   *[no] Conversation sans rien à retenir
}

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
   *[unknown] { $person } : position inconnue
}

journal-satellite-pairing-requested = Satellite { $device } ({ $model }, { $room }) demande à être appairé
journal-detail-declares = { $count ->
    [0] Déclare : aucune capacité
   *[other] Déclare : { $capabilities }
}
journal-satellite-paired = { $proof ->
    [enrollment_code] Satellite { $device } appairé avec un code d'ajout ({ $room })
   *[device_code] Satellite { $device } appairé avec son code ({ $room })
}
journal-detail-allowed = { $count ->
    [0] Autorisé : aucune capacité
   *[other] Autorisé : { $capabilities }
}
journal-satellite-revoked = Satellite { $device } révoqué
journal-satellite-connected = Satellite { $device } connecté ({ $room })
journal-satellite-disconnected = Satellite { $device } déconnecté ({ $room })
journal-detail-software = { $name } { $version }
journal-satellite-update-requested = { $device } : mise à jour de { $running } vers { $target } demandée
journal-satellite-update-reported = { $state ->
    [available] { $device } : version { $target } disponible
    [installing] { $device } installe { $target }
    [failed] { $device } : échec de { $target }, retour à la version précédente
   *[current] { $device } est à jour
}
journal-satellite-addition-started = { $proof ->
    [enrollment_code] Code d'ajout créé pour un satellite
   *[device_code] Ajout d'un satellite par son code
}
journal-satellite-addition-completed = Satellite { $device } ajouté
journal-satellite-addition-cancelled = Ajout de satellite annulé
journal-satellite-addition-expired = Ajout de satellite expiré
journal-satellite-enrollment-refused = { $reason ->
    [expired] { $device } a présenté un code d'ajout expiré
    [used] { $device } a présenté un code d'ajout déjà utilisé
    [cancelled] { $device } a présenté un code d'ajout annulé
   *[unknown] { $device } a présenté un mauvais code d'ajout
}
journal-satellite-identify-requested = { $device } : identification demandée
journal-person-detected = { $count ->
    [one] { $count } personne vue par { $device } ({ $room })
   *[other] { $count } personnes vues par { $device } ({ $room })
}
journal-detail-confidence = Confiance : { NUMBER($confidence, style: "percent") }
journal-speech-activity = { $active ->
    [yes] Parole détectée près de { $device } ({ $room })
   *[no] Fin de parole près de { $device } ({ $room })
}

journal-account-created = Compte { $login } créé ({ role-name })
journal-account-role-changed = Compte { $login } : rôle { role-name }
journal-account-disabled = Compte { $login } désactivé
journal-account-enabled = Compte { $login } réactivé
journal-account-password-changed = Mot de passe du compte { $login } changé
journal-account-locale-changed = { $chosen ->
    [no] Compte { $login } : langue du foyer
   *[yes] Compte { $login } : langue { $locale }
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

journal-speaker-declared = { $person } a donné son nom
journal-voice-enrolled = Voix de { $person } enregistrée ({ $where })
journal-voice-forgotten = { $learned ->
    [yes] Apprentissage de la voix de { $person } effacé
   *[no] Voix de { $person } effacée
}
journal-voice-learning = { $learning ->
    [yes] Apprentissage de la voix de { $person } activé
   *[no] Apprentissage de la voix de { $person } désactivé
}
journal-confirmation-requested = Confirmation demandée par écrit à { $person } : { $tool }
journal-confirmation-answered = { $approved ->
    [yes] Confirmé par écrit
   *[no] Refusé par écrit
}

journal-behavior-changed = État : { $behavior ->
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
journal-system-update-requested = Mise à jour de { $running } vers { $target } demandée { $via ->
    [cli] depuis la ligne de commande
   *[admin] par { $login }
}
journal-system-update-failed = Échec de l'installation de { $target } : Nestor reste sur sa version
