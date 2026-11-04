## Système : ce que l'instance a assemblé au démarrage, et l'état de chaque pièce.

sys-title = Système
sys-started = démarré
sys-unwell = { $count ->
    [one] 1 composant à surveiller
   *[other] { $count } composants à surveiller
}
sys-all-well = tout va bien
sys-slot-model = Modèles
sys-slot-speech = Parole
sys-slot-executor = Exécutants
sys-slot-channel = Canaux
sys-slot-presence = Présence
sys-slot-tools = Outils
sys-slot-connector = Connecteurs
sys-slot-satellite = Satellites
sys-slot-storage = Stockage et exécution
sys-health-ok = ok
sys-health-degraded = dégradé
sys-health-down = en panne
sys-health-unknown = inconnu

## Mises à jour : une version plus récente de Nestor, ce qui a changé et comment l'installer.

upd-available = Nouvelle version
upd-available-version = Mise à jour disponible : { $version }
upd-title = Nestor { $version } est là
upd-description = Ce qui a changé depuis votre version.
upd-behind = { $count ->
    [one] une version de retard
   *[other] { $count } versions de retard
}
upd-breaking = Cette version change les données ou la configuration : relisez les notes avant de mettre à jour.
upd-by-hand = Mettez Nestor à jour comme vous l'avez installé, puis redémarrez-le.
upd-release = Version { $version }
upd-notes = Notes de version
upd-kind-breaking = Ruptures
upd-kind-feature = Nouveautés
upd-kind-fix = Corrections
upd-kind-other = Autres
