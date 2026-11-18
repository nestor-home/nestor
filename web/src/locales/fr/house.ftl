## Maison : le système domotique (Home Assistant), tel que Nestor le voit.

house-lede = Il sait { $granularity }. Lumières, chauffage et médias ne demandent aucune confirmation ; ce que vous marquez sensible, si.
house-configure = Configurer
house-none = Aucun système domotique branché.
house-none-hint = Reliez Home Assistant : présence, pièces et actions au même endroit.
house-people = Personnes suivies
house-not-tied = non relié : présence inconnue
house-actions = Actions
house-actions-empty = Aucune action disponible.
house-actions-empty-hint = Le serveur MCP du système domotique ne répond pas, ou n'expose rien à Assist.
house-action-confirmed-when = confirmée selon sa cible
house-unplaced = { $count ->
    [one] 1 capteur de présence n'a pas de pièce : il est ignoré.
   *[other] { $count } capteurs de présence n'ont pas de pièce : ils sont ignorés.
}
house-strangers = { $count ->
    [one] Il connaît aussi { $names }, relié à personne du foyer.
   *[other] Il connaît aussi { $names }, reliés à personne du foyer.
}

## L'espace « La maison »
hs-lede = Qui vit ici, où chacun se trouve, et par quoi { $assistant } entend, parle et voit dans chaque pièce.
hs-system = Système domotique
hs-people = Le foyer
hs-rooms = Les pièces
hs-rooms-empty = Aucune pièce connue : ajoutez un satellite ou reliez un système domotique.
hs-media = Voir et appeler
hs-room-events = { $count ->
    [one] 1 fois aujourd'hui
   *[other] { $count } fois aujourd'hui
}
hs-memories = { $count ->
    [one] Un souvenir gardé par { $assistant }
   *[other] { $count } souvenirs gardés par { $assistant }
}
hs-media-off = Voir et appeler sont coupés sur ce serveur.
hs-media-off-hint = Installez Nestor avec l'extra « media » pour relayer l'image et le son des appareils.
hs-add-person = Ajouter une personne
