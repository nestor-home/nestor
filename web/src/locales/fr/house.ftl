## Maison : le système domotique (Home Assistant), tel que Nestor le voit.

house-title = Maison
house-lede = Elle sait { $granularity }. Lumières, chauffage et médias ne demandent aucune confirmation ; ce que vous marquez sensible, si.
house-configure = Configurer
house-none = Aucun système domotique branché.
house-none-hint = Reliez Home Assistant : présence, pièces et actions au même endroit.
house-people = Qui est où
house-not-tied = non relié : présence inconnue
house-rooms = Pièces
house-rooms-empty = Aucune pièce dans le système domotique.
house-room-occupied = occupée
house-room-empty = vide
house-room-people = personnes
house-room-satellites = satellites
house-room-nobody = personne de connu
house-residents = Connus du système domotique
house-resident-tied = relié à { $name }
house-resident-untied = relié à personne
house-actions = Actions
house-actions-empty = Aucune action disponible.
house-actions-empty-hint = Le serveur MCP du système domotique ne répond pas, ou n'expose rien à Assist.
house-action-confirmed-when = confirmée selon sa cible
house-unplaced = { $count ->
    [one] 1 capteur de présence n'a pas de pièce : il est ignoré.
   *[other] { $count } capteurs de présence n'ont pas de pièce : ils sont ignorés.
}
