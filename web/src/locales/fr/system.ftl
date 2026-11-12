## Système : ce que l'instance a assemblé au démarrage, et l'état de chaque pièce.

sys-title = Système
sys-started = démarré
sys-unwell = { $count ->
    [one] 1 composant à surveiller
   *[other] { $count } composants à surveiller
}
sys-all-well = tout va bien
sys-slot-model = Modèles
sys-slot-executor = Exécutants
sys-slot-channel = Canaux
sys-slot-home = Maison
sys-slot-tools = Outils
sys-slot-inbound = Sources entrantes
sys-slot-connector = Connecteurs
sys-slot-satellite = Satellites
sys-health-ok = ok
sys-health-degraded = dégradé
sys-health-down = en panne
sys-health-unknown = inconnu

## Mises à jour : une version plus récente de Nestor, ce qui a changé et comment l'installer.

upd-available = Nouvelle version
upd-available-version = Mise à jour disponible : { $version }
upd-title = Nestor { $version } est là
upd-description = Notes de version et mise à jour.
upd-behind = { $count ->
    [one] une version de retard
   *[other] { $count } versions de retard
}
upd-install = Installer la { $version }
upd-install-title = Installer Nestor { $version } ?
upd-install-description = Nestor installe la nouvelle version, vérifie votre configuration, puis redémarre. En cas d'échec, il reste sur la { $running }.
upd-install-confirm = Installer et redémarrer
upd-install-hint = Redémarrage après l'installation.
upd-installing = Installation de la { $version }…
upd-failed = La { $version } ne s'est pas installée. Nestor reste sur la { $running }.
upd-breaking = Cette version change les données ou la configuration : relisez les notes avant de mettre à jour.
upd-outdated = { $count ->
    [one] Ce satellite ne pourra plus se connecter : mettez-le à jour sur l’appareil, après le serveur.
   *[other] Ces { $count } satellites ne pourront plus se connecter : mettez-les à jour sur chaque appareil, après le serveur.
}
upd-release = Version { $version }
upd-notes = Notes de version
upd-kind-breaking = Ruptures
upd-kind-feature = Nouveautés
upd-kind-fix = Corrections
upd-kind-other = Autres
upd-how = Mettre à jour
upd-how-container = Dans le dossier de compose.yaml :
upd-how-uv-tool = Sur la machine de Nestor :
upd-how-pip = Sur la machine de Nestor :
upd-how-editable = Nestor tourne depuis un checkout : mettez-le à jour avec git.
upd-then-restart = Puis redémarrez Nestor.
upd-then-ask = Puis demandez à un administrateur de redémarrer Nestor.
upd-command = la commande
