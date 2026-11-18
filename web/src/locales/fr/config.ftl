## Configuration : le fichier de configuration, édité par sections, ses secrets, son historique, le redémarrage.

cfg-title = Configuration
cfg-intro = Vérifié avant d'être écrit, appliqué au prochain redémarrage.
cfg-nav = Parties de la configuration
cfg-group-agent = L'agent
cfg-group-household = Le foyer
cfg-group-talk = Comment il parle et écoute
cfg-group-reach = Ce qu'il peut atteindre
cfg-group-install = L'installation
cfg-switch = Sections
cfg-about-persona = Son nom, son caractère et la langue de ses réponses.
cfg-about-initiative = Quand il peut prendre la parole de lui-même, et où.
cfg-about-memory = Combien de souvenirs et de conversations passées nourrissent chaque réponse.
cfg-about-household = Les personnes qu'il connaît par leur nom : comment un canal reconnaît chacune, et où lui écrire.
cfg-about-voices = Reconnaître qui parle sur un appareil partagé, à sa voix. Il faut un modèle de reconnaissance du locuteur.
cfg-about-models = Les modèles avec lesquels il réfléchit, entend et parle, puis lequel sert chaque rôle.
cfg-about-channels = Là où on lui parle : satellites des pièces, messageries, cet admin.
cfg-about-home = Le système de la maison : il dit qui est là et dans quelle pièce, et exécute ce qu'on demande à la maison.
cfg-about-connectors = Les services dont une personne peut connecter un compte (mail, agenda, tâches). Chaque compte s'ajoute ensuite dans Connexions.
cfg-about-tools = Ce qu'il peut chercher ou faire seul : recherche web, météo, lieux, serveurs MCP.
cfg-about-inbound = Ce qu'il suit pour les veilles : flux, pages, webhooks.
cfg-about-executors = Les agents à qui il confie les tâches longues.
cfg-about-admin = Où cette interface est servie, et l'adresse par laquelle on y accède.
cfg-about-updates = S'il cherche les nouvelles versions. Rien ne s'installe seul.
cfg-sum-people = { $count ->
    [0] Personne pour l'instant
    [one] 1 personne
   *[other] { $count } personnes
}
cfg-sum-needed = Rien encore : il en faut un pour démarrer
cfg-sum-none = Rien de configuré
cfg-sum-more = { $names } et { $count } de plus
cfg-sum-extra = +{ $count }
cfg-sum-defaults = Réglages par défaut
cfg-sum-secrets = { $count ->
    [0] Aucun secret
    [one] 1 secret
   *[other] { $count } secrets
}
cfg-sum-secrets-unset = { $count } secrets, dont { $unset } sans valeur
cfg-sum-history = { $count ->
    [0] Aucune version précédente
    [one] 1 version précédente
   *[other] { $count } versions précédentes
}
cfg-unknown-page = Cette partie de la configuration n'existe pas.
cfg-modified = modifié

## Les formulaires
cfg-advanced = { $count ->
    [one] Avancé · 1 réglage
   *[other] Avancé · { $count } réglages
}
cfg-default = Par défaut ({ $value })
cfg-list-default = Vide : { $value } par défaut.
cfg-list-empty = Aucun élément.
cfg-add-item-to = Ajouter à { $field }
cfg-add-item = Ajouter
cfg-add-entry = Ajouter une entrée
cfg-item-n = élément { $n }
cfg-item-of = { $field }, élément { $n }
cfg-map-key = { $field }, nom { $n }
cfg-map-value = { $field }, valeur de { $key }
cfg-move-up = Monter { $item }
cfg-move-down = Descendre { $item }
cfg-remove-item = Retirer { $item }
cfg-edit-item = Modifier { $item }
cfg-json-invalid = JSON invalide : corrigez-le, sinon la valeur précédente reste.
cfg-secret-set = défini · { $preview }
cfg-secret-unset = non défini
cfg-secret-reference = référence { $reference }
cfg-secret-replace = Remplacer
cfg-secret-replace-label = Remplacer { $field }
cfg-secret-keep = Garder l'actuel
cfg-secret-placeholder = nouvelle valeur
cfg-secret-typed = nouvelle valeur, pas encore enregistrée

## Les pages
cfg-settings = Réglages
cfg-edit = Modifier
cfg-unset = Non défini
cfg-on = Activé
cfg-off = Désactivé
cfg-entries = { $count ->
    [one] 1 entrée
   *[other] { $count } entrées
}
cfg-people = Personnes
cfg-person-no-account = Aucun compte sur un canal
cfg-people-empty = Personne dans le foyer pour l'instant.
cfg-add-person = Ajouter une personne
cfg-remove-person-title = Retirer { $name } du foyer ?
cfg-remove-person-text = La personne disparaît du fichier au prochain enregistrement ; ses comptes et souvenirs restent dans la base.
cfg-reference-default = Par défaut
cfg-name = Nom
cfg-name-help = Les autres réglages s'y réfèrent : le renommer les met à jour.
cfg-name-taken = Ce nom est déjà pris.
cfg-name-invalid = Lettres, chiffres, « _ », « . » et « - », en commençant par une lettre ou un chiffre.
cfg-add-kind = Ajouter { $kind }
cfg-required-fields = { $count ->
    [0] rien d'obligatoire
    [one] 1 réglage obligatoire
   *[other] { $count } réglages obligatoires
}
cfg-slot-none = Rien de configuré ici.
cfg-slot-required = Il en faut au moins un pour démarrer.
cfg-slot-optional = Facultatif.
cfg-no-plugin = Aucun plugin de ce type n'est installé.
cfg-no-plugin-hint = Installez-en un dans l'environnement de Nestor, puis redémarrez.
cfg-kind-missing = Le plugin « { $kind } » n'est pas installé : ce composant ne peut pas démarrer.
cfg-kind-missing-short = non installé
cfg-remove = Retirer
cfg-remove-title = Retirer { $name } ?
cfg-remove-text = Le composant disparaît du fichier au prochain enregistrement. Ses secrets restent dans le coffre.
cfg-sheet-note = Les changements vont dans le brouillon : rien n'est écrit avant « Enregistrer ».
cfg-done = Terminé
cfg-cancel-add = Annuler l'ajout

## Enregistrer
cfg-save-region = Modifications non enregistrées
cfg-checking = vérification…
cfg-problems = { $count ->
    [one] 1 problème
   *[other] { $count } problèmes
}
cfg-changes = { $count ->
    [one] 1 modification
   *[other] { $count } modifications
}
cfg-changes-title = Modifications
cfg-changes-text = Ce que l'enregistrement écrira dans le fichier. Les secrets ne sont jamais montrés.
cfg-change-added = ajouté
cfg-change-removed = retiré
cfg-change-changed = modifié
cfg-change-becomes = devient
cfg-change-secret = secret modifié
cfg-no-change = Aucune modification.
cfg-discard = Annuler les modifications
cfg-discard-title = Abandonner les modifications ?
cfg-discard-text = Le brouillon revient au fichier tel qu'il est écrit.
cfg-discard-confirm = Abandonner
cfg-save = Enregistrer
cfg-saving = Enregistrement…
cfg-saved = C'est noté : je l'appliquerai au prochain redémarrage.
cfg-leave-title = Quitter sans enregistrer ?
cfg-leave-text = Les modifications de la configuration seront perdues.
cfg-leave-stay = Rester
cfg-leave-go = Quitter

## Redémarrer
cfg-restart-required = Redémarrage requis
cfg-pending = { $count ->
    [0] la configuration a changé
    [one] 1 changement en attente
   *[other] { $count } changements en attente
}
cfg-pending-show = voir ce qui attend
cfg-restart = Redémarrer…
cfg-restart-ask = Un administrateur doit redémarrer l'instance.
cfg-restart-title = Redémarrer { $agent } ?
cfg-restart-text = { $agent } s'arrête proprement puis repart avec la même commande, quelques secondes en général.
cfg-restart-channels = Les canaux se ferment : une conversation en cours est coupée.
cfg-restart-tasks = Les tâches déléguées continuent ; leur suivi reprend après.
cfg-restart-apply = { $count ->
    [one] Le changement enregistré s'applique.
   *[other] Les changements enregistrés s'appliquent.
}
cfg-restart-now = Redémarrer maintenant
cfg-restarting = Je redémarre, à tout de suite.
cfg-restarting-hint = La page reprend d'elle-même.
cfg-restarting-slow = C'est plus long que d'habitude : vérifiez le journal du service si rien ne revient.
cfg-restart-done = Me revoilà : la configuration est appliquée.

cfg-restart-signed-out = Me revoilà, configuration appliquée. Reconnectez-vous pour continuer.

## Secrets
cfg-secrets = Secrets
cfg-secrets-intro = Chiffrés, hors du fichier, qui y renvoie par ${"{"}secret:nom{"}"}. Jamais réaffichés.
cfg-secrets-list = Coffre
cfg-secrets-empty = Aucun secret.
cfg-secrets-empty-hint = Un secret tapé dans un formulaire y est rangé à l'enregistrement.
cfg-secret-new = Nouveau secret
cfg-secret-define = Définir
cfg-secret-used-by = Utilisé par
cfg-secret-unused = Utilisé nulle part.
cfg-secret-replace-title = Remplacer { $name }
cfg-secret-form-text = La valeur est chiffrée et ne sera plus jamais affichée, seulement un aperçu.
cfg-secret-name = Nom
cfg-secret-name-hint = Par exemple tools.maison.token ; le fichier y fait référence par ${"{"}secret:nom{"}"}.
cfg-secret-value = Valeur
cfg-secret-save = Enregistrer
cfg-secret-saved = Secret { $name } enregistré.
cfg-secret-delete = Supprimer
cfg-secret-delete-label = Supprimer { $name }
cfg-secret-delete-title = Supprimer { $name } ?
cfg-secret-delete-text = La valeur est effacée du coffre ; rien ne permet de la retrouver.
cfg-secret-in-use-text = La configuration l'utilise encore : les réglages concernés ne pourront plus démarrer.
cfg-secret-delete-anyway = Supprimer quand même
cfg-secret-deleted = Secret { $name } supprimé.

## Historique
cfg-history = Historique
cfg-history-intro = Chaque enregistrement garde la version précédente.
cfg-history-versions = Versions précédentes
cfg-history-empty = Aucune version précédente.
cfg-history-empty-hint = La première apparaît au premier enregistrement depuis l'admin.
cfg-history-size = { $size } octets
cfg-history-kind = Version précédente
cfg-history-would = { $count ->
    [one] Restaurer changerait 1 réglage.
   *[other] Restaurer changerait { $count } réglages.
}
cfg-history-same = Identique au fichier actuel.
cfg-history-invalid = Cette version n'est plus utilisable telle quelle :
cfg-restore = Restaurer
cfg-restore-title = Restaurer cette version ?
cfg-restore-text = Le fichier actuel part dans l'historique ; la version choisie s'appliquera au prochain redémarrage.
cfg-restore-dirty = Enregistrez ou annulez d'abord vos modifications en cours.
cfg-restored = Version restaurée : un redémarrage l'appliquera.
cfg-pick-type = Type de modèle
cfg-model-type = { $type ->
    [language] Langage
    [embedding] Embeddings
    [speaker] Voix reconnue
    [transcription] Transcription
    [speech] Synthèse vocale
    [image] Images
   *[other] Autre
}
cfg-add-one = { $slot ->
    [models] Ajouter un modèle
    [channels] Ajouter un canal
    [executors] Ajouter un exécutant
    [tools] Ajouter un outil
    [inbound] Ajouter une source
    [home] Relier un système domotique
    [connectors] Ajouter un connecteur
   *[other] Ajouter à « { $title } »
}
cfg-pick-model = Ce qu'il fera, puis qui le fournit.
cfg-pick-text = Ce que cette installation sait brancher.
