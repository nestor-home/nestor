## What the mock server renders in French, as Nestor's own `.ftl` will (server-owned messages).

journal-presence-room = { $name } est dans la pièce « { $room } »
journal-presence-away = { $name } n'est plus à la maison
journal-person-detected = { $count ->
    [one] 1 personne vue
   *[other] { $count } personnes vues
} par { $device } (pièce « { $room } »)
journal-speech-detected = Parole détectée près de { $device } (pièce « { $room } »)
journal-user-said = { $name } a dit
journal-assistant-answered = { $assistant } a répondu
journal-assistant-interrupted = { $assistant } a répondu (interrompu)
journal-answer-cut = Réponse coupée par { $name }
journal-fallback = Réponse de secours : { $reason ->
    [model_slow] modèle trop lent
    [model_unavailable] modèle indisponible
   *[other] { $reason }
}
journal-tool-called = Outil { $tool } appelé
journal-tool-done = Outil { $tool } terminé en { $duration }
journal-tool-failed = Outil { $tool } en échec
journal-task-started = Tâche { $task } confiée à { $executor }
journal-task-progressed = Tâche { $task } : nouvelle étape
journal-task-completed = Tâche { $task } terminée ({ $duration })
journal-task-failed = Tâche { $task } en échec ({ $duration })
journal-watch-created = Veille créée : { $what }
journal-watch-triggered = Veille { $watch } déclenchée par « { $item } »
journal-watch-triaged = Tri : pertinent pour { $name }
journal-watch-triaged-urgent = Tri : pertinent, à signaler aujourd'hui
journal-subject = { $subject ->
    [task] tâche { $ref }{ $done ->
        [yes] {" "}terminée
       *[no] {""}
    }
    [watch] veille { $ref }
   *[other] { $ref }
}
journal-delivery-considered = Décision de { $written ->
    [yes] écrire
   *[no] parler
} à { $name } : { journal-subject }{ $follow_up ->
    [yes] {" "}(relance)
   *[no] {""}
}
journal-delivered = Message transmis { $spoken ->
    [yes] à voix haute
   *[no] par écrit
} : { journal-subject }{ $follow_up ->
    [yes] {" "}(relance)
   *[no] {""}
}
journal-delivery-failed = Message non transmis{ $spoken ->
    [yes] {" "}à voix haute
   *[no] {""}
} : { journal-subject }
journal-connection-needs-reauth = Connexion { $account } à réautoriser
journal-connection-created = Compte { $account } connecté ({ $service })
journal-pairing-requested = Le satellite { $device } ({ $model }, pièce « { $room } ») demande l'appairage
journal-memory-recorded = Souvenir enregistré

reason-in-room = { $name } est dans la pièce « { $room } »
reason-away = { $name } n'est pas à la maison
reason-no-presence = aucune information de présence : retour à la conversation d'origine
reason-no-reply-away = pas de réponse depuis { $minutes } min, et { $name } n'est pas à la maison

error-bad-credentials = Adresse ou mot de passe incorrect.
error-account-disabled = Ce compte est désactivé : demandez au propriétaire du foyer.
error-session-expired = Votre session a expiré : reconnectez-vous.
error-csrf = Formulaire expiré : rechargez la page.
error-invitation-unknown = Cette invitation n'existe pas, a expiré ou a déjà servi.
error-weak-password = Le mot de passe doit faire au moins { $min } caractères.
error-account-exists = Un compte existe déjà pour cette adresse.
error-last-owner = Le foyer doit garder au moins un propriétaire actif.
error-resource-not-found = { $what } introuvable.
error-client-incomplete = Indiquez l'identifiant et le secret du client OAuth.
error-client-missing = Enregistrez d'abord le client OAuth.
error-fields-missing = Champs manquants : { $fields }.
error-provider-refused = Le service a refusé la connexion : identifiants rejetés par le serveur.
error-pairing-refused = Aucun appareil n'attend ce code : il est faux ou a expiré.
error-memory-empty = Un souvenir ne peut pas être vide : oubliez-le plutôt.
error-invitation-person = Un compte membre ou invité appartient à une personne du foyer.

## Configuration (copied from Nestor's locales/fr/config.ftl and errors.ftl)
config-error-missing = { $path } : obligatoire.
config-error-extra = { $path } : réglage inconnu.
config-error-invalid = { $path } : { $detail }
config-error-unknown-kind = { $path } : aucun greffon « { $detail } » n'est installé.
config-error-reference = { $path } : la variable d'environnement { $detail } n'est pas définie.
config-error-secret = { $path } : le secret { $detail } n'est pas défini.
error-config-unavailable = Cette instance n'a pas démarré depuis un fichier de configuration : rien à modifier.
error-no-secret-key = NESTOR_SECRET_KEY n'est pas définie : impossible de garder des secrets sans elle.
error-config-invalid = La configuration est inutilisable ({ $count ->
    [one] un problème
   *[other] { $count } problèmes
}) : rien n'a été écrit.
error-config-history-unknown = Cette configuration antérieure n'existe pas.
error-secret-in-use = Ce secret sert encore à { $paths } : retirez d'abord ces références.
error-secret-unknown = Ce secret n'est pas défini.
error-restart-unconfirmed = Confirmez le redémarrage : chaque conversation sera interrompue un instant.
