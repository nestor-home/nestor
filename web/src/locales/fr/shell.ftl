## Le cadre de chaque écran : navigation, ligne d'état, menu du compte, palette de commandes.

nav-journal = Journal
nav-people = Personnes
nav-memories = Souvenirs
nav-connections = Connexions
nav-satellites = Satellites
nav-system = Système
nav-usage = Coûts
nav-accounts = Comptes
nav-config = Configuration

shell-skip = Aller au contenu
shell-home-link = { $assistant } · Nestor
shell-sections = Sections
shell-account-menu = Menu du compte
shell-theme = Thème
shell-theme-system = Système
shell-theme-light = Clair
shell-theme-dark = Sombre
shell-language = Langue
shell-sign-out = Se déconnecter
shell-display = Affichage
shell-theme-to-light = Passer en clair
shell-theme-to-dark = Passer en sombre

shell-live-connecting = connexion…
shell-version = nestor { $version }
shell-go-to = Aller à…
shell-palette-description = Chercher une section, une personne, un service
shell-palette-placeholder = Section, personne, connexion…
shell-palette-empty = Aucun résultat.
shell-palette-theme-keywords = thème clair sombre

attention-reauth = { $account } est à réautoriser
attention-connection-error = { $account } ne répond plus
attention-tools-hidden = Ses outils sont suspendus.
attention-reconnect = Reconnecter
attention-confirmation = { $tool } attend votre accord
attention-confirmation-detail = Sans réponse, abandonné à { $at }.
attention-answer = Répondre
attention-home = { $health ->
    [unavailable] Le système domotique ne répond pas
   *[other] Le système domotique répond en partie
}
attention-pairing = { $device } attend d'être appairé
attention-pairing-detail = { $model }, « { $room } » : saisissez le code qu'il affiche.
attention-approve = Approuver
attention-satellite-offline = { $device } est hors ligne
attention-satellite-offline-detail = Il n'écoute plus et ne parle plus dans « { $room } ».
attention-understand = Détails
attention-task-failed = La tâche « { $title } » a échoué
attention-task-waiting = « { $title } » attend une réponse
attention-component-down = { $name } est en panne
shell-agent-offline = hors ligne
shell-agent-label = { $assistant }, { $state }

## Les espaces de la barre
space-today = Aujourd'hui
space-chat = Parler
space-activity = En cours
space-house = La maison
space-settings = Réglages

## Réglages
set-lede = Ce dont { $assistant } est fait : les services qu'il utilise, les appareils des pièces, qui a accès à quoi.
set-connections = Comptes et services dont il se sert : mail, agenda, outils.
set-connections-count = { $count ->
    [0] Aucune connexion
    [one] Une connexion
   *[other] { $count } connexions
}
set-satellites = Les appareils par lesquels il entend, parle et voit dans chaque pièce.
set-satellites-count = { $count ->
    [0] Aucun appareil
    [one] Un appareil
   *[other] { $count } appareils
}
set-satellites-offline = { $count } appareils, dont { $offline } hors ligne
set-accounts = Qui peut ouvrir cette interface, et avec quels droits.
set-accounts-count = { $count ->
    [one] Un compte
   *[other] { $count } comptes
}
set-config = Modèles, voix, canaux, maison : tout ce qui règle { $assistant }.
set-usage = Ce que coûte chaque modèle, pour qui et pour quoi.
set-usage-month = { $spent } ce mois-ci
set-system = L'état de chaque composant, les mises à jour, le redémarrage.
shell-space-waiting = { $space }, { $count ->
    [one] une demande vous attend
   *[other] { $count } demandes vous attendent
}
shell-rail-fold = Replier la barre
shell-rail-unfold = Déplier la barre
