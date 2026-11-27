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

journal-task-created = Tâche { $task } ouverte avec { $executor } : { $title }
journal-task-renamed = Tâche { $task } renommée : { $title }
journal-task-archived = Tâche { $task } archivée
journal-task-turn-started = Tâche { $task } : nouvelle consigne
journal-task-turn-attached = Tâche { $task } prise en charge par l'exécutant
journal-task-turn-step = Tâche { $task } : nouvelle étape
journal-task-turn-retried = Tâche { $task } relancée dans une nouvelle session : son exécutant avait perdu la précédente
journal-task-steered = Tâche { $task } { $taken ->
    [yes] réorientée en cours de travail
   *[no] arrêtée pour une nouvelle consigne
}
journal-task-turn-stop-requested = Arrêt demandé pour la tâche { $task }
journal-task-turn-ended = Tâche { $task } { $status ->
    [completed] revenue
    [asked] pose une question
    [failed] en échec
    [stopped] arrêtée
   *[other] { $status }
} ({ NUMBER($seconds, maximumFractionDigits: 0) } s)
journal-task-turn-delivered = Retour de la tâche { $task } transmis
journal-task-turn-file-added = Tâche { $task } : un fichier rendu
journal-task-noted = Tâche { $task } : une note gardée
journal-task-reminded = La tâche { $task } attend toujours une réponse : rappel envoyé
journal-executor-called = { $ok ->
    [yes] { $executor } a utilisé { $tool }
   *[no] { $executor } s'est vu refuser { $tool }
}
journal-executor-key-issued = Nouvelle clé pour { $executor }
journal-executor-key-revoked = Clé de { $executor } révoquée

journal-subject = { $subject ->
    [task] tâche { $id } { $status ->
        [completed] terminée
        [failed] en échec
        [cancelled] annulée
       *[other] { $status }
    }
    [alert] alerte { $id }
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

journal-alert-created = { $trigger ->
    [at] Alerte programmée : { $title }
    [times] Alerte régulière programmée : { $title }
   *[events] Alerte sur { $kinds } : { $title }
}
journal-alert-sorted = { $unsorted ->
    [yes] « { $item } » non trié : le modèle n'a pas répondu
   *[no] { $matched ->
        [0] « { $item } » vérifié pour { $asked } { $asked ->
            [one] alerte
           *[other] alertes
        } : aucune ne correspond
       *[other] « { $item } » vérifié pour { $asked } { $asked ->
            [one] alerte
           *[other] alertes
        } : { $matched } { $matched ->
            [one] correspond
           *[other] correspondent
        }
    }
}
journal-alert-rang = L'alerte { $alert } a sonné : { $cause ->
    [due] c'était l'heure
    [event] l'événement { $kind } est arrivé (« { $item } »)
   *[match] « { $item } » correspond
}
journal-alert-ended = Alerte { $alert } { $reason ->
    [rang] terminée : elle a sonné
    [cancelled] annulée
    [expired] expirée
    [left] terminée : la personne qui l'a créée a quitté le foyer
   *[done] terminée : plus rien ne peut la faire sonner
}

journal-memory-place = { $shelf ->
    [home] la maison
    [household] le foyer
   *[other] { $name }
}
journal-memory-recorded = { $drawn ->
    [yes] Souvenir tiré d'une conversation, dans { journal-memory-place }
   *[no] { $kept ->
        [yes] Note de tâche gardée comme souvenir, dans { journal-memory-place }
       *[no] Souvenir enregistré dans { journal-memory-place }
    }
}
journal-memory-corrected = { $merged ->
    [0] Souvenir corrigé
    [one] Souvenir fusionné avec un autre pendant l'entretien de la nuit
   *[other] Souvenir fusionné avec { $merged } autres pendant l'entretien de la nuit
}
journal-memory-moved = Souvenir déplacé dans { journal-memory-place }
journal-memory-forgotten = Souvenir oublié
journal-memory-retired = { $reason ->
    [ended] { $tie ->
        [task] Souvenir retiré : sa tâche est terminée
       *[other] Souvenir retiré : ce à quoi il tenait est terminé
    }
    [merged] Souvenir fusionné dans un autre
   *[stale] Souvenir retiré car périmé
}
journal-memory-upkept = { $failed ->
    [0] Entretien des souvenirs de la nuit : { $merged } fusionnés, { $retired } retirés
   *[other] Entretien des souvenirs de la nuit : { $merged } fusionnés, { $retired } retirés, { $failed } places non lues
}
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
journal-satellite-media-access = { $device } : { $viewers ->
    [0] personne d'autre que les propriétaires ne peut le regarder
    [one] une personne peut le regarder
   *[other] { $viewers } personnes peuvent le regarder
}, { $callers ->
    [0] personne d'autre que les propriétaires ne peut appeler par lui
    [one] une personne peut appeler par lui
   *[other] { $callers } personnes peuvent appeler par lui
}, caméra { $camera ->
    [off] coupée
   *[on] allumée
}
journal-media-opened = { $purpose ->
    [call] Appel par { $device } ({ $room })
   *[view] { $device } regardé ({ $room })
}
journal-media-closed = { $device } : session terminée après { $seconds } s, { $reason ->
    [timed_out] sa durée maximale est passée
    [signed_out] la personne s'est déconnectée
    [access_changed] la personne n'y a plus droit
    [camera_off] { $off ->
        [quiet_hours] les heures calmes de la caméra ont commencé
        [someone_home] une personne pour qui la caméra se coupe est rentrée
       *[other] la caméra a été coupée
    }
    [device_left] l'appareil est parti
    [failed] elle n'a pas pu s'ouvrir
   *[closed] fermée
}
journal-media-snapshot = Image prise par { $device } ({ $room })
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
journal-confirmation-requested = Confirmation demandée à { $person } : { $tool }
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
journal-usage-recorded = { $consumer } pour { usage-purpose } : { USD($cost) }
journal-usage-unknown = { $consumer } pour { usage-purpose } : coût inconnu
