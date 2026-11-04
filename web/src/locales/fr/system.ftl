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
upd-title = Nestor { $version } est disponible
upd-running = { $count ->
    [one] Vous utilisez la { $version }. Voici ce qui a changé depuis.
   *[other] Vous utilisez la { $version }, avec { $count } versions de retard. Voici ce qui a changé depuis.
}
upd-breaking = Cette version change les données ou la configuration : relisez les notes avant de mettre à jour.
upd-outdated = { $count ->
    [one] Ce satellite ne pourra plus se connecter : mettez-le à jour avant.
   *[other] Ces { $count } satellites ne pourront plus se connecter : mettez-les à jour avant.
}
upd-release = Version { $version }
upd-notes = Notes de version
upd-kind-breaking = Ruptures
upd-kind-feature = Nouveautés
upd-kind-fix = Corrections
upd-kind-other = Autres
upd-how = Mettre à jour
upd-how-container = Nestor tourne dans un conteneur : récupérez la nouvelle image, puis relancez-le, dans le dossier de compose.yaml.
upd-how-package = Sur la machine de Nestor, mettez à jour le paquet :
upd-how-pip = Ou, s'il a été installé avec pip :
upd-then-restart = Puis redémarrez Nestor pour lancer la nouvelle version.
upd-then-ask = Puis demandez à un administrateur de redémarrer Nestor.
upd-command = la commande
